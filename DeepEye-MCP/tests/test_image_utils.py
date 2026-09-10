"""``deepeye_mcp.image_utils`` 单元测试。

覆盖三种图像来源（本地文件 / 公网 URL / Base64 data URI）的解析逻辑，
URL 下载通过 mock ``httpx.AsyncClient`` 避免真实网络 IO。
"""

from __future__ import annotations

import base64
import io
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepeye_mcp.config import settings
from deepeye_mcp.image_utils import (
    _parse_data_uri,
    load_image_as_base64,
    load_image_from_url_as_base64,
    parse_image_source,
    preprocess_image,
)


def _write_png(path: Path) -> bytes:
    """用 Pillow 生成一张最小 PNG 写入 ``path``，返回图片原始 bytes。"""
    from PIL import Image

    img = Image.new("RGB", (2, 2), color=(255, 0, 0))
    img.save(path, format="PNG")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# load_image_as_base64
# ---------------------------------------------------------------------------


def test_load_image_as_base64_local_png(tmp_path: Path):
    img_path = tmp_path / "test.png"
    raw = _write_png(img_path)
    expected_b64 = base64.b64encode(raw).decode("ascii")

    b64_data, mime_type = load_image_as_base64(str(img_path))

    assert b64_data == expected_b64
    assert mime_type == "image/png"


def test_load_image_as_base64_file_not_found(tmp_path: Path):
    missing = tmp_path / "nope.png"
    with pytest.raises(FileNotFoundError):
        load_image_as_base64(str(missing))


def test_load_image_as_base64_unknown_extension(tmp_path: Path, monkeypatch):
    """mimetypes 推断失败（返回 None）时应回退到默认 ``image/png``。

    使用 monkeypatch 强制 ``mimetypes.guess_type`` 返回 ``None``，避免
    不同操作系统下扩展名映射差异（如 Windows 上 ``.bin`` 会返回
    ``application/octet-stream``）造成测试不稳定。
    """
    import mimetypes

    monkeypatch.setattr(mimetypes, "guess_type", lambda path: (None, None))

    img_path = tmp_path / "weird.xyz"
    raw = b"\x89PNG\r\n\x1a\nfake-bytes"
    img_path.write_bytes(raw)
    expected_b64 = base64.b64encode(raw).decode("ascii")

    b64_data, mime_type = load_image_as_base64(str(img_path))

    assert b64_data == expected_b64
    assert mime_type == "image/png"


# ---------------------------------------------------------------------------
# _parse_data_uri
# ---------------------------------------------------------------------------


def test_parse_data_uri_jpeg():
    b64_data, mime_type = _parse_data_uri("data:image/jpeg;base64,/9j/4AAQ")
    assert b64_data == "/9j/4AAQ"
    assert mime_type == "image/jpeg"


def test_parse_data_uri_png():
    b64_data, mime_type = _parse_data_uri("data:image/png;base64,iVBOR")
    assert b64_data == "iVBOR"
    assert mime_type == "image/png"


def test_parse_data_uri_empty_data_raises():
    with pytest.raises(ValueError):
        _parse_data_uri("data:image/png;base64,")


# ---------------------------------------------------------------------------
# load_image_from_url_as_base64（mock httpx）
# ---------------------------------------------------------------------------


# 公网 IP，用于 mock DNS 解析（避免测试依赖真实 DNS）
_PUBLIC_IP = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


class _FakeStream:
    """``client.stream(...)`` 的异步上下文管理器替身。"""

    def __init__(self, response: MagicMock) -> None:
        self._response = response

    async def __aenter__(self) -> MagicMock:
        return self._response

    async def __aexit__(self, *exc_info) -> bool:
        return False


def _make_fake_response(
    content: bytes,
    content_type: str = "image/png",
    status_code: int = 200,
) -> MagicMock:
    """构造 fake 响应，支持流式下载路径（headers / aiter_bytes）。"""
    fake_response = MagicMock()
    fake_response.status_code = status_code
    fake_response.headers = (
        {"Content-Type": content_type} if content_type else {}
    )
    fake_response.raise_for_status = MagicMock()

    async def _aiter_bytes(chunk_size: int = 65536):
        for i in range(0, len(content), chunk_size):
            yield content[i : i + chunk_size]

    fake_response.aiter_bytes = _aiter_bytes
    return fake_response


def _make_fake_client(
    content: bytes = b"",
    content_type: str = "image/png",
    *,
    response: MagicMock | None = None,
) -> AsyncMock:
    """构造 fake ``httpx.AsyncClient``。

    下载路径现在走 ``client.stream("GET", ...)``（流式 + 边读边限幅），
    因此替身需要提供 ``stream`` 而非 ``get``。
    """
    if response is None:
        response = _make_fake_response(content, content_type)
    fake_client = AsyncMock()
    fake_client.stream = MagicMock(side_effect=lambda *a, **k: _FakeStream(response))
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    return fake_client


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_load_image_from_url_as_base64(mock_client_cls, mock_getaddrinfo):
    raw = b"fake-image-bytes"
    mock_client_cls.return_value = _make_fake_client(raw, "image/jpeg; charset=utf-8")

    b64_data, mime_type = await load_image_from_url_as_base64(
        "https://example.com/cat.jpg"
    )

    assert b64_data == base64.b64encode(raw).decode("ascii")
    assert mime_type == "image/jpeg"
    mock_client_cls.return_value.stream.assert_called_once_with(
        "GET", "https://example.com/cat.jpg"
    )


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_load_image_from_url_as_base64_missing_content_type(mock_client_cls, mock_getaddrinfo):
    raw = b"more-bytes"
    mock_client_cls.return_value = _make_fake_client(raw, "")

    b64_data, mime_type = await load_image_from_url_as_base64(
        "https://example.com/img"
    )

    assert b64_data == base64.b64encode(raw).decode("ascii")
    assert mime_type == "image/png"


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_load_image_from_url_as_base64_raises_on_error_status(mock_client_cls, mock_getaddrinfo):
    import httpx

    fake_response = _make_fake_response(b"", "image/png", status_code=500)
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Internal Server Error",
        request=MagicMock(),
        response=fake_response,
    )
    mock_client_cls.return_value = _make_fake_client(response=fake_response)

    with pytest.raises(httpx.HTTPStatusError):
        await load_image_from_url_as_base64("https://example.com/500.png")


# ---------------------------------------------------------------------------
# SSRF 防护 + 大小上限
# ---------------------------------------------------------------------------


async def _assert_ssrf_blocked(host: str, ip: str, url: str) -> None:
    """断言解析到 ``ip`` 的 ``host`` 被 SSRF 防护拒绝。"""
    with patch(
        "deepeye_mcp.image_utils.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))],
    ):
        with pytest.raises(ValueError, match="SSRF"):
            await load_image_from_url_as_base64(url)


async def test_url_rejects_localhost_ip():
    await _assert_ssrf_blocked("example.com", "127.0.0.1", "https://example.com/x.png")


async def test_url_rejects_private_ip():
    await _assert_ssrf_blocked("intranet", "10.0.0.1", "http://intranet/secret")


async def test_url_rejects_link_local_metadata():
    await _assert_ssrf_blocked(
        "metadata", "169.254.169.254", "http://metadata/latest/meta-data"
    )


async def test_url_rejects_loopback_hostname():
    await _assert_ssrf_blocked("localhost", "127.0.0.1", "http://localhost:11434/v1")


async def test_allow_private_urls_bypasses_ssrf(monkeypatch):
    """allow_private_urls=True 时跳过 SSRF 校验（仅本地调试）。"""
    monkeypatch.setattr(settings, "allow_private_urls", True)
    with patch("deepeye_mcp.image_utils.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_fake_client(b"x", "image/png")
        b64_data, mime_type = await load_image_from_url_as_base64(
            "http://127.0.0.1/img.png"
        )

    assert b64_data == base64.b64encode(b"x").decode("ascii")
    assert mime_type == "image/png"


async def test_url_too_large_rejected(monkeypatch):
    """下载内容超过 max_image_bytes 上限时应拒绝。"""
    monkeypatch.setattr(settings, "max_image_bytes", 10)
    with patch(
        "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
    ):
        with patch("deepeye_mcp.image_utils.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_fake_client(b"x" * 100, "image/png")
            with pytest.raises(ValueError, match="大小上限"):
                await load_image_from_url_as_base64("https://example.com/big.png")


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_url_streaming_aborts_before_reading_everything(
    mock_client_cls, mock_getaddrinfo, monkeypatch
):
    """流式下载必须在超限时立刻中断，而不是读完整个响应体再判断。"""
    monkeypatch.setattr(settings, "max_image_bytes", 8)
    raw = b"x" * (64 * 1024)  # 远大于上限，会被切成多个 64KB 分块
    mock_client_cls.return_value = _make_fake_client(raw, "image/png")

    with pytest.raises(ValueError, match="大小上限"):
        await load_image_from_url_as_base64("https://example.com/huge.png")


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_url_rejects_non_image_content_type(mock_client_cls, mock_getaddrinfo):
    """返回 HTML 错误页（Content-Type: text/html）时应拒绝。

    否则错误页会被 base64 编码后当作图片送进视觉模型，产生无意义调用。
    """
    mock_client_cls.return_value = _make_fake_client(
        b"<html>404 not found</html>", "text/html; charset=utf-8"
    )

    with pytest.raises(ValueError, match="不是图片"):
        await load_image_from_url_as_base64("https://example.com/missing.png")


# ---------------------------------------------------------------------------
# parse_image_source（统一入口）
# ---------------------------------------------------------------------------


async def test_parse_image_source_data_uri_no_io():
    """``data:`` 前缀走 _parse_data_uri，不进行任何文件/网络 IO。"""
    b64_data, mime_type = await parse_image_source("data:image/png;base64,ABC")
    assert b64_data == "ABC"
    assert mime_type == "image/png"


async def test_parse_image_source_local(tmp_path: Path):
    img_path = tmp_path / "local.png"
    raw = _write_png(img_path)

    b64_data, mime_type = await parse_image_source(str(img_path))

    assert b64_data == base64.b64encode(raw).decode("ascii")
    assert mime_type == "image/png"


@patch(
    "deepeye_mcp.image_utils.socket.getaddrinfo", return_value=_PUBLIC_IP
)
@patch("deepeye_mcp.image_utils.httpx.AsyncClient")
async def test_parse_image_source_url(mock_client_cls, mock_getaddrinfo):
    raw = b"webp-bytes"
    mock_client_cls.return_value = _make_fake_client(raw, "image/webp")

    b64_data, mime_type = await parse_image_source("https://example.com/img.webp")

    assert b64_data == base64.b64encode(raw).decode("ascii")
    assert mime_type == "image/webp"


# ---------------------------------------------------------------------------
# preprocess_image
# ---------------------------------------------------------------------------


def _make_image_b64(size: tuple[int, int], fmt: str = "PNG") -> tuple[str, str]:
    """用 Pillow 生成指定尺寸图片并返回 ``(base64, mime)``。"""
    from PIL import Image

    img = Image.new("RGB", size, color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    mime = f"image/{fmt.lower()}"
    return base64.b64encode(buf.getvalue()).decode("ascii"), mime


def test_preprocess_image_downscale_large_image(monkeypatch):
    """超大图（3000x3000）超过 max_dim=2048 时应等比缩放到 2048x2048。"""
    monkeypatch.setattr(settings, "image_max_dim", 2048)
    from PIL import Image

    b64, mime = _make_image_b64((3000, 3000), "PNG")
    new_b64, new_mime = preprocess_image(b64, mime)

    assert new_mime == "image/jpeg"
    # 缩放后应为 2048x2048
    with Image.open(io.BytesIO(base64.b64decode(new_b64))) as img:
        assert img.size == (2048, 2048)
        assert img.format == "JPEG"
    # 新 base64 应与原始不同
    assert new_b64 != b64


def test_preprocess_image_downscale_keeps_aspect_ratio(monkeypatch):
    """非正方形图（3000x1500）应按比例缩放到 (2048, 1024)。"""
    monkeypatch.setattr(settings, "image_max_dim", 2048)
    from PIL import Image

    b64, mime = _make_image_b64((3000, 1500), "PNG")
    new_b64, new_mime = preprocess_image(b64, mime)

    assert new_mime == "image/jpeg"
    with Image.open(io.BytesIO(base64.b64decode(new_b64))) as img:
        assert img.size == (2048, 1024)


def test_preprocess_image_small_image_unchanged(monkeypatch):
    """小图（100x100）两边均小于 max_dim，应原样返回。"""
    monkeypatch.setattr(settings, "image_max_dim", 2048)
    b64, mime = _make_image_b64((100, 100), "PNG")

    new_b64, new_mime = preprocess_image(b64, mime)

    assert new_b64 == b64
    assert new_mime == mime


def test_preprocess_image_disabled_when_max_dim_zero(monkeypatch):
    """image_max_dim=0 时禁用预处理，原样返回（即使是超大图）。"""
    monkeypatch.setattr(settings, "image_max_dim", 0)
    b64, mime = _make_image_b64((3000, 3000), "PNG")

    new_b64, new_mime = preprocess_image(b64, mime)

    assert new_b64 == b64
    assert new_mime == mime


def test_preprocess_image_invalid_base64_returns_original(monkeypatch):
    """无效 base64 解码失败时应原样返回，不抛异常。"""
    monkeypatch.setattr(settings, "image_max_dim", 2048)
    invalid_b64 = "not-a-valid-base64!!!"
    original_mime = "image/png"

    new_b64, new_mime = preprocess_image(invalid_b64, original_mime)

    assert new_b64 == invalid_b64
    assert new_mime == original_mime


def test_preprocess_image_corrupt_image_bytes_returns_original(monkeypatch):
    """能解码为 base64 但不是有效图片数据时，应原样返回。"""
    monkeypatch.setattr(settings, "image_max_dim", 2048)
    # 有效 base64 但内容非图片
    corrupt_b64 = base64.b64encode(b"not an image at all").decode("ascii")
    original_mime = "image/png"

    new_b64, new_mime = preprocess_image(corrupt_b64, original_mime)

    assert new_b64 == corrupt_b64
    assert new_mime == original_mime
