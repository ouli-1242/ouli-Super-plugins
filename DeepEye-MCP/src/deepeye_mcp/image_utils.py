"""图像源解析工具。

统一处理三种图像来源：
- 本地文件路径
- 公网 URL（http/https）
- Base64 data URI（``data:image/...;base64,...``）

所有解析函数最终返回 ``(base64_data, mime_type)`` 元组。
"""

from __future__ import annotations

import base64
import io
import ipaddress
import mimetypes
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps

from deepeye_mcp.config import settings
from deepeye_mcp.errors import ImageSourceError

_DEFAULT_MIME = "image/png"

# 流式下载分块大小：边读边累计，超限立刻中断，避免把超大响应读进内存
_DOWNLOAD_CHUNK_SIZE = 64 * 1024


def _is_public_ip(ip: str) -> bool:
    """判断 IP 是否为公网地址。

    内网 / 回环 / 链路本地 / 保留 / 组播 / 未指定地址均视为非公网。
    """
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _ensure_public_target(url: str) -> str:
    """校验 URL 指向公网地址，防止 SSRF。

    解析主机名到 IP，任一解析结果落在内网/保留地址即拒绝；
    ``settings.allow_private_urls=True`` 时跳过校验（仅本地调试）。

    Raises:
        ImageSourceError: URL 无法解析或解析到非公网地址时抛出。
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ImageSourceError("URL 缺少主机名")
    if settings.allow_private_urls:
        return hostname

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ImageSourceError(f"无法解析主机: {hostname}") from exc

    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise ImageSourceError(
                f"拒绝访问非公网地址（SSRF 防护）: {hostname} ({ip})"
            )
    return hostname


def load_image_as_base64(path: str) -> tuple[str, str]:
    """同步读取本地图片文件并返回 ``(base64_data, mime_type)``。

    Args:
        path: 本地图片文件路径。

    Returns:
        ``(base64_data, mime_type)`` 元组。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ImageSourceError: 文件超过 ``settings.max_image_bytes`` 时抛出。
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"图像文件不存在: {path}")

    # 先看文件大小再读：避免把超大文件整块读进内存后才发现超限
    size = p.stat().st_size
    if size > settings.max_image_bytes:
        raise ImageSourceError(
            f"图片超过大小上限: {size} > {settings.max_image_bytes} bytes (本地文件)"
        )

    data = p.read_bytes()
    b64_data = base64.b64encode(data).decode("ascii")
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type is None:
        mime_type = _DEFAULT_MIME
    return b64_data, mime_type


async def load_image_from_url_as_base64(url: str) -> tuple[str, str]:
    """异步下载 URL 图片并返回 ``(base64_data, mime_type)``。

    手动跟随重定向（不用 ``follow_redirects=True``，避免 SSRF 绕过）：
    每一跳都对目标 URL 重新执行公网校验，全链合法才实际请求。

    Args:
        url: 以 ``http://`` 或 ``https://`` 开头的图片地址。

    Returns:
        ``(base64_data, mime_type)`` 元组。MIME 从响应 ``Content-Type``
        推断（取 ``;`` 之前部分），无法推断时默认 ``image/png``。

    Raises:
        ImageSourceError: 重定向异常、SSRF 拦截、超过大小上限、或
            响应 ``Content-Type`` 不是 ``image/*``。
        httpx.HTTPStatusError: 目标返回非 2xx 状态码。

    Note:
        响应体**流式**读取并边读边计，超限立即中断——避免把超大响应
        整块读进内存（历史实现先 ``response.content`` 再比大小）。
    """
    _MAX_REDIRECTS = 5
    current = url
    chunks: list[bytes] = []
    mime_type = ""
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=settings.request_timeout
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            _ensure_public_target(current)
            async with client.stream("GET", current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if not location:
                        raise ImageSourceError(f"重定向缺少 Location 头: {current}")
                    # 解析相对重定向；下一跳会重新做公网校验
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
            break
        else:
            raise ImageSourceError(f"重定向次数超过上限: {_MAX_REDIRECTS}")

    if not mime_type:
        mime_type = _DEFAULT_MIME
    return base64.b64encode(b"".join(chunks)).decode("ascii"), mime_type


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


def _check_size(data: bytes, label: str) -> None:
    """校验图片字节数是否超过 ``settings.max_image_bytes``，超限抛 ImageSourceError。"""
    if len(data) > settings.max_image_bytes:
        raise ImageSourceError(
            f"图片超过大小上限: {len(data)} > {settings.max_image_bytes} bytes ({label})"
        )


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
    """统一图像源解析入口。

    根据前缀自动选择解析策略：
    - ``data:`` 开头 → 直接解析 data URI，不进行 IO
    - ``http://`` / ``https://`` 开头 → 异步下载
    - 其他 → 视为本地路径

    三种来源均受 ``settings.max_image_bytes`` 大小上限约束：本地路径在读取
    前用 ``stat`` 校验、URL 边下载边限幅、data URI 解码后校验，均不会把
    超限内容整块留在内存里。

    Args:
        image_source: 图像来源字符串。

    Returns:
        ``(base64_data, mime_type)`` 元组。
    """
    if image_source.startswith("data:"):
        b64_data, mime_type = _parse_data_uri(image_source)
        try:
            raw = base64.b64decode(b64_data, validate=True)
        except Exception:
            # 数据无法按标准 base64 解码时不阻断，交给后续视觉后端处理
            return b64_data, mime_type
        _check_size(raw, "data URI")
        return b64_data, mime_type
    if image_source.startswith(("http://", "https://")):
        return await load_image_from_url_as_base64(image_source)
    # 本地路径：大小校验在读取前用 stat 完成（见 load_image_as_base64），
    # 这里不再为「量尺寸」而把整个 base64 二次解码
    return load_image_as_base64(image_source)


def preprocess_image(b64: str, mime: str) -> tuple[str, str]:
    """图片预处理：超过最大边长时等比缩放并转 JPEG 以减小体积。

    处理规则：
    - ``settings.image_max_dim == 0`` 时禁用预处理，原样返回 ``(b64, mime)``。
    - 图片最大边未超过 ``image_max_dim`` 时原样返回。
    - 超过则等比缩放到 ``image_max_dim``，再以 JPEG 重新编码，
      返回的 ``mime`` 改为 ``image/jpeg``。
    - Pillow 解码/处理任何异常时原样返回（不阻断主流程，保证健壮性）。

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
        with Image.open(io.BytesIO(raw)) as img:
            orig_size = img.size
            # 应用 EXIF 方向标记：手机竖拍图 Orientation!=1 时先转正，
            # 否则缩放/转 JPEG 后 OCR 与描述会侧向
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            longest = max(width, height)
            if longest <= max_dim:
                # 仅当 EXIF 转正改变了尺寸（如竖拍 100x50 -> 50x100）才需要重编码，
                # 否则原样返回（与历史行为一致，避免无谓重编码）
                if img.size != orig_size:
                    buffer = io.BytesIO()
                    img.convert("RGB").save(buffer, format="JPEG", quality=90)
                    new_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                    return new_b64, "image/jpeg"
                return b64, mime

            # 等比缩放
            scale = max_dim / longest
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.convert("RGB")
            img = img.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            new_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
            return new_b64, "image/jpeg"
    except Exception:
        # 任何解码/处理异常均原样返回，不阻断主流程
        return b64, mime
