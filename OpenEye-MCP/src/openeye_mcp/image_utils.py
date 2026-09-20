"""图像源解析工具。

统一处理三种图像来源：
- 本地文件路径
- 公网 URL（http/https）
- Base64 data URI（``data:image/...;base64,...``）

所有解析函数最终返回 ``(base64_data, mime_type)`` 元组。

安全边界
--------
本模块是「模型可以给服务器任意输入」的第一道闸，因此：

1. **SSRF**：URL 主机名只做一次 DNS 解析，校验通过后**直接连到该 IP**
   （URL 改写为 IP + 保留原 ``Host`` 头 + ``sni_hostname`` 固定证书校验），
   消除「先解析校验、再独立解析连接」之间的 DNS rebinding 窗口。
2. **网段**：以 :attr:`ipaddress.IPv4Address.is_global` 为准；
   ``is_private`` 单独用会漏掉 100.64.0.0/10（CGNAT，阿里云元数据端点
   ``100.100.100.200`` 正在其中）等等效内网段。
3. **代理**：取图 client 关闭 ``trust_env``，否则环境里的 ``HTTP_PROXY``
   会让代理去做解析，本地校验形同虚设。
4. **内容**：三种来源都强制过一遍图片解码校验，避免把 HTML 错误页、
   文本文件乃至任意本地文件内容当成「图片」送进第三方 API。
5. **本地路径**：``ALLOWED_IMAGE_ROOTS`` 非空时目录白名单生效。
"""

from __future__ import annotations

import asyncio
import base64
import io
import ipaddress
import mimetypes
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from openeye_mcp.config import settings
from openeye_mcp.errors import ImageSourceError

_DEFAULT_MIME = "image/png"

# 流式下载分块大小：边读边累计，超限立刻中断，避免把超大响应读进内存
_DOWNLOAD_CHUNK_SIZE = 64 * 1024

_MAX_REDIRECTS = 5


def _is_public_ip(ip: str) -> bool:
    """判断 IP 是否可安全外发请求。

    用 ``is_global`` 而非 ``is_private`` 取反：后者漏掉 CGNAT 100.64.0.0/10
    （阿里云元数据 ``100.100.100.200``）等不在 ``is_private`` 内的非公网段。
    """
    try:
        return ipaddress.ip_address(ip.split("%")[0]).is_global
    except ValueError:
        return False


async def _pin_public_address(url: str) -> tuple[str, str, int]:
    """校验 URL 指向公网并返回 ``(改写为 IP 的 URL, 原主机名, 端口)``。

    解析与校验只做一次，调用方随后直接连接返回的 IP，因此不存在
    「校验一个 IP、连接另一个 IP」的 rebinding 窗口。
    ``settings.allow_private_urls=True`` 时跳过校验（仅本地调试），
    此时仍返回 IP 字面量形式的 URL 以保持调用方行为一致。

    Raises:
        ImageSourceError: URL 缺少主机名、协议非 http(s) 或解析到非公网地址。
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ImageSourceError("URL 缺少主机名")
    if parsed.scheme not in ("http", "https"):
        raise ImageSourceError(f"仅支持 http(s) 图片地址，得到 {parsed.scheme!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        # 注意：asyncio 没有模块级 getaddrinfo，只有事件循环上的方法
        infos = await asyncio.get_running_loop().getaddrinfo(
            hostname, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ImageSourceError(f"无法解析主机: {hostname}") from exc
    ips = [str(info[4][0]) for info in infos]
    if not ips:
        raise ImageSourceError(f"无法解析主机: {hostname}")

    if not settings.allow_private_urls:
        for ip in ips:
            if not _is_public_ip(ip):
                raise ImageSourceError(
                    f"拒绝访问非公网地址（SSRF 防护）: {hostname} ({ip})"
                )
    return _with_host(url, ips[0], port), hostname, port


def _with_host(url: str, ip: str, port: int) -> str:
    """把 URL 的 host 替换为已校验的 IP（IPv6 加方括号）。"""
    parsed = urlparse(url)
    literal = f"[{ip}]" if ":" in ip else ip
    netloc = literal if port in (80, 443) else f"{literal}:{port}"
    return parsed._replace(netloc=netloc).geturl()


def _target_headers(hostname: str, port: int) -> dict[str, str]:
    """连 IP 时保持原主机名的 ``Host`` 头（虚拟主机依赖它路由）。"""
    host_header = hostname if port in (80, 443) else f"{hostname}:{port}"
    return {"Host": host_header}


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _check_size(data: bytes, label: str) -> None:
    """校验图片字节数是否超过 ``settings.max_image_bytes``，超限抛 ImageSourceError。"""
    if len(data) > settings.max_image_bytes:
        raise ImageSourceError(
            f"图片超过大小上限: {len(data)} > {settings.max_image_bytes} bytes ({label})"
        )


def _ensure_decodable_image(data: bytes, label: str) -> None:
    """确认字节确实是可解码图片。

    没有这道校验时，``/etc/hosts``、HTML 错误页或任意本地文本文件都会被
    当作 ``image/png`` 送进第三方视觉 API —— 既是数据外泄，也是白花钱。
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageSourceError(f"内容不是可识别的图片: {label}（{exc}）") from exc


def _ensure_within_allowed_roots(path: str) -> Path:
    """按 ``ALLOWED_IMAGE_ROOTS`` 校验本地路径；返回解析后的绝对路径。"""
    resolved = Path(path).expanduser().resolve()
    roots = settings.image_roots
    if roots and not any(_is_within(resolved, root) for root in roots):
        raise ImageSourceError(
            f"本地路径不在 ALLOWED_IMAGE_ROOTS 白名单内: {path}"
        )
    return resolved


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _read_local(path: str) -> tuple[bytes, str]:
    """读取本地图片字节并推断 MIME；先查大小再读，避免超大文件进内存。

    Raises:
        FileNotFoundError: 文件不存在。
        ImageSourceError: 路径不在白名单内或超过大小上限。
    """
    resolved = _ensure_within_allowed_roots(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"图像文件不存在: {path}")

    size = resolved.stat().st_size
    if size > settings.max_image_bytes:
        raise ImageSourceError(
            f"图片超过大小上限: {size} > {settings.max_image_bytes} bytes (本地文件)"
        )
    data = resolved.read_bytes()
    mime_type, _ = mimetypes.guess_type(path)
    return data, mime_type or _DEFAULT_MIME


def load_image_as_base64(path: str) -> tuple[str, str]:
    """同步读取本地图片文件并返回 ``(base64_data, mime_type)``。

    不做图片内容校验（那是 :func:`parse_image_source` 的职责），供需要
    原始读取语义的调用方使用。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ImageSourceError: 路径不合法或超过 ``settings.max_image_bytes``。
    """
    data, mime_type = _read_local(path)
    return _encode(data), mime_type


async def load_image_from_url_as_base64(url: str) -> tuple[str, str]:
    """异步下载 URL 图片并返回 ``(base64_data, mime_type)``。

    手动跟随重定向（不用 ``follow_redirects=True``）：每一跳重新做一次
    「解析 + 公网校验 + IP 固定」，全链合法才实际请求。

    Args:
        url: 以 ``http://`` 或 ``https://`` 开头的图片地址。

    Returns:
        ``(base64_data, mime_type)`` 元组。MIME 取响应 ``Content-Type``
        的 ``;`` 之前部分，缺失时默认 ``image/png``。

    Raises:
        ImageSourceError: SSRF 拦截、重定向异常、非图片响应、或超过大小上限。
        httpx.HTTPStatusError: 目标返回非 2xx 状态码。
    """
    current = url
    chunks: list[bytes] = []
    mime_type = ""
    # trust_env=False：不能让环境里的 HTTP_PROXY 代替我们做解析与连接
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=settings.request_timeout, trust_env=False
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            pinned_url, hostname, port = await _pin_public_address(current)
            request = client.build_request(
                "GET", pinned_url, headers=_target_headers(hostname, port)
            )
            # 连的是 IP，但 TLS 的 SNI 与证书主机名校验仍按原主机名进行
            request.extensions["sni_hostname"] = hostname
            response = await client.send(request, stream=True)
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if not location:
                        raise ImageSourceError(f"重定向缺少 Location 头: {current}")
                    # 相对重定向按当前地址解析；下一跳会重新校验
                    current = str(httpx.URL(current).join(location))
                    continue
                response.raise_for_status()
                _ensure_image_content_type(response, current)

                content_type = response.headers.get("Content-Type", "")
                mime_type = content_type.split(";")[0].strip() if content_type else ""
                total = 0
                async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_SIZE):
                    total += len(chunk)
                    if total > settings.max_image_bytes:
                        raise ImageSourceError(
                            f"图片超过大小上限: > {settings.max_image_bytes} bytes "
                            f"(下载中断, {current})"
                        )
                    chunks.append(chunk)
            finally:
                await response.aclose()
            break
        else:
            raise ImageSourceError(f"重定向次数超过上限: {_MAX_REDIRECTS}")

    data = b"".join(chunks)
    await asyncio.to_thread(_ensure_decodable_image, data, current)
    return _encode(data), mime_type or _DEFAULT_MIME


def _parse_data_uri(image_source: str) -> tuple[str, str]:
    """解析 ``data:image/...;base64,...`` 形式的 data URI。

    Args:
        image_source: data URI 字符串。

    Returns:
        ``(base64_data, mime_type)`` 元组。
    """
    # 形如: data:image/jpeg;base64,/9j/...
    header, _, b64_data = image_source.partition(",")
    # header 形如: data:image/jpeg;base64
    mime_type = _DEFAULT_MIME
    if header.startswith("data:"):
        meta = header[len("data:") :]  # image/jpeg;base64
        if ";" in meta:
            mime_type = meta.split(";")[0].strip() or _DEFAULT_MIME
        elif meta:
            mime_type = meta.strip() or _DEFAULT_MIME
    if not b64_data:
        raise ImageSourceError("data URI 不含 base64 数据")
    return b64_data, mime_type


def _ensure_image_content_type(response: httpx.Response, url: str) -> None:
    """拒绝 ``Content-Type`` 明显不是图片的响应。

    服务器常以 ``200 OK`` 返回 HTML 错误页（``text/html``）。若不过滤，
    它会被 base64 编码后当作图片送进视觉模型，产生无意义的调用与费用。
    未带 ``Content-Type`` 的响应不做判断（部分静态服务器会省略该头）。
    """
    content_type = response.headers.get("Content-Type", "")
    if not content_type:
        return
    mime = content_type.split(";")[0].strip().lower()
    if mime and not mime.startswith("image/"):
        raise ImageSourceError(f"URL 返回的不是图片（Content-Type: {mime}）: {url}")


async def parse_image_source(image_source: str) -> tuple[str, str]:
    """统一图像源解析入口（含图片内容校验）。

    根据前缀自动选择解析策略：
    - ``data:`` 开头 → 直接解析 data URI，不进行 IO
    - ``http://`` / ``https://`` 开头 → 异步下载
    - 其他 → 视为本地路径

    三种来源均受 ``settings.max_image_bytes`` 大小上限约束：本地路径在读取
    前用 ``stat`` 校验、URL 边下载边限幅、data URI 解码后校验，均不会把
    超限内容整块留在内存里。文件读取、base64 解码与 Pillow 校验都放进
    线程执行，避免阻塞 stdio 的事件循环。

    Args:
        image_source: 图像来源字符串。

    Returns:
        ``(base64_data, mime_type)`` 元组。

    Raises:
        ImageSourceError: 来源非法、被 SSRF 拦截、超限或内容不是图片。
        FileNotFoundError: 本地文件不存在。
    """
    if image_source.startswith("data:"):
        b64_data, mime_type = _parse_data_uri(image_source)
        try:
            raw = base64.b64decode(b64_data, validate=True)
        except Exception:
            # 无法按标准 base64 解码时不在此处阻断，交给后端报错
            return b64_data, mime_type
        _check_size(raw, "data URI")
        await asyncio.to_thread(_ensure_decodable_image, raw, "data URI")
        return b64_data, mime_type

    if image_source.startswith(("http://", "https://")):
        return await load_image_from_url_as_base64(image_source)

    # 本地路径：大小校验在读取前用 stat 完成（见 _read_local），
    # 这里不再为「量尺寸」而把整个 base64 二次解码
    data, mime_type = await asyncio.to_thread(_read_local, image_source)
    await asyncio.to_thread(_ensure_decodable_image, data, image_source)
    return _encode(data), mime_type


def preprocess_image(b64: str, mime: str) -> tuple[str, str]:
    """图片预处理：超过最大边长时等比缩放并转 JPEG 以减小体积。

    处理规则：
    - ``settings.image_max_dim == 0`` 时禁用预处理，原样返回 ``(b64, mime)``。
    - 图片最大边未超过 ``image_max_dim`` 时原样返回。
    - 超过则等比缩放到 ``image_max_dim``，再以 JPEG 重新编码，
      返回的 ``mime`` 改为 ``image/jpeg``。
    - Pillow 处理任何异常时原样返回（不阻断主流程，保证健壮性）。

    纯 CPU 操作，异步调用方应通过 ``asyncio.to_thread`` 调它。

    Args:
        b64: 原始图片的 base64 字符串。
        mime: 原始图片的 MIME 类型。

    Returns:
        ``(new_b64, new_mime)`` 元组。
    """
    max_dim = settings.image_max_dim
    if not max_dim or max_dim <= 0:
        return b64, mime

    try:
        raw = base64.b64decode(b64)
        with Image.open(io.BytesIO(raw)) as opened:
            orig_size = opened.size
            # 应用 EXIF 方向标记：手机竖拍图 Orientation!=1 时先转正，
            # 否则缩放/转 JPEG 后 OCR 与描述会侧向
            img = ImageOps.exif_transpose(opened)
            width, height = img.size
            longest = max(width, height)
            if longest <= max_dim:
                # 仅当 EXIF 转正改变了尺寸（如竖拍 100x50 -> 50x100）才需要重编码，
                # 否则原样返回（与历史行为一致，避免无谓重编码）
                if img.size != orig_size:
                    buffer = io.BytesIO()
                    img.convert("RGB").save(buffer, format="JPEG", quality=90)
                    return _encode(buffer.getvalue()), "image/jpeg"
                return b64, mime

            # 等比缩放
            scale = max_dim / longest
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            resized = img.convert("RGB").resize(new_size, Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=90)
            return _encode(buffer.getvalue()), "image/jpeg"
    except Exception:
        # 任何解码/处理异常均原样返回，不阻断主流程
        return b64, mime
