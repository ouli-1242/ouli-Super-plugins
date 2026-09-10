"""DeepEye 审查修复回归测试（基于审查报告声明 1-11 新增）。

覆盖：
- 声明 1: 工具失败经 server.call_tool 返回 isError=True
- 声明 2: SSRF 重定向链逐跳校验（拒绝重定向到内网）
- 声明 3: extract_text 按 ocr_backend 指定 provider
- 声明 4: Gemini json_object 映射 responseMimeType
- 声明 5: analyze_images 并发受 Semaphore 限制
- 声明 6: data URI / 本地路径超限被拒绝
- 声明 7: EXIF 方向转正
- 声明 8: gemini 复用模块级 client
- 声明 9: detail 非法值返回 isError；analyze_images 空数组返回 isError
"""

from __future__ import annotations

import base64
import io
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.types import CallToolResult

from deepeye_mcp.config import settings
from deepeye_mcp.errors import VisionError
from deepeye_mcp.image_utils import load_image_from_url_as_base64, parse_image_source, preprocess_image
from deepeye_mcp.server import call_tool
from deepeye_mcp.tools import analyze_images, extract_text
from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter

_PUBLIC_IP = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _params(**kwargs):
    m = MagicMock()
    m.name = kwargs.pop("_name", "")
    m.arguments = kwargs
    return m


# ---------------------------------------------------------------------------
# 声明 1: isError
# ---------------------------------------------------------------------------


async def test_call_tool_failure_sets_is_error():
    """工具失败时 server 层应返回 isError=True。"""
    for name, args in [
        ("describe_image", {"image_source": "/nonexistent/nope.png"}),
        ("extract_text", {"image_source": "/nonexistent/nope.png"}),
        ("ask_about_image", {"image_source": "/nonexistent/nope.png", "question": "q"}),
        ("extract_table", {"image_source": "/nonexistent/nope.png"}),
    ]:
        with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
            mf.side_effect = RuntimeError("boom")
            result = await call_tool(None, _params(_name=name, **args))
        assert isinstance(result, CallToolResult)
        assert result.is_error is True, f"{name} 失败未置 isError"
        assert len(result.content) == 1


# ---------------------------------------------------------------------------
# 声明 2: SSRF 重定向逐跳校验
# ---------------------------------------------------------------------------


async def test_redirect_to_internal_rejected():
    """公网 URL 重定向到内网时应被拒绝（每跳复检）。"""
    # 第一跳: 初始 URL -> 200 且 Location 指向内网（301）
    seen_urls = []

    async def fake_get(url, *a, **k):
        seen_urls.append(url)
        fr = MagicMock()
        fr.content = b"x"
        fr.headers = {"Content-Type": "image/png"}
        fr.status_code = 200
        fr.raise_for_status = MagicMock()
        return fr

    fc = AsyncMock()
    fc.get = fake_get
    fc.__aenter__.return_value = fc
    fc.__aexit__.return_value = None

    # 第一次 get 返回 301 指向内网；手动逻辑应校验 Location 目标后拒绝
    with patch("deepeye_mcp.image_utils._ensure_public_target") as m_ensure:
        m_ensure.side_effect = [None, ValueError("拒绝访问非公网地址（SSRF 防护）: 127.0.0.1 (127.0.0.1)")]

        async def fake_get_redirect(url, *a, **k):
            seen_urls.append(url)
            fr = MagicMock()
            fr.status_code = 301
            # httpx.Headers 不区分大小写；用真实 Headers 构造
            fr.headers = httpx.Headers({"Location": "http://127.0.0.1:8080/internal.png"})
            return fr

        fc.get = fake_get_redirect
        with patch("deepeye_mcp.image_utils.httpx.AsyncClient", return_value=fc):
            with pytest.raises(ValueError, match="SSRF"):
                await load_image_from_url_as_base64("https://example.com/x.png")

    # 校验函数对初始 URL 和重定向目标都被调用
    ensure_calls = m_ensure.call_count
    assert ensure_calls >= 2, f"应逐跳校验（初始+重定向目标），实际 {ensure_calls} 次"


# ---------------------------------------------------------------------------
# 声明 3: extract_text 用 ocr_backend
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.tools.create_vision_adapter")
async def test_extract_text_uses_ocr_backend_provider(mock_factory):
    """extract_text 应按 settings.ocr_backend 指定 provider。"""
    monkeypatch = None
    from deepeye_mcp.config import settings as _s
    _s.ocr_backend = "gemini"
    adapter = MagicMock()
    adapter.describe = AsyncMock(return_value="OCR 结果")
    mock_factory.return_value = adapter

    await extract_text(image_source="data:image/png;base64,AAA")

    mock_factory.assert_called_once_with(None, provider="gemini")


# ---------------------------------------------------------------------------
# 声明 4: Gemini json_object
# ---------------------------------------------------------------------------


async def test_gemini_json_object_maps_mime_type():
    """response_format json_object 应映射 generationConfig.responseMimeType。"""
    captured = {}

    async def fake_post(url, params=None, json=None, headers=None, **k):
        captured["json"] = json
        fr = MagicMock()
        fr.raise_for_status = MagicMock()
        fr.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "{}"}]}}]
        })
        return fr

    with patch("deepeye_mcp.config.settings.gemini_api_key", "k"):
        with patch("deepeye_mcp.config.settings.request_timeout", 5):
            with patch("deepeye_mcp.config.settings.max_retries", 0):
                with patch("deepeye_mcp.vision.gemini_adapter._get_client") as m:
                    m.return_value.post = fake_post
                    adapter = GeminiVisionAdapter(model="gemini-x", api_key="k")
                    await adapter.describe(
                        "b64", "image/png", "p", response_format={"type": "json_object"}
                    )
    gen = captured["json"].get("generationConfig", {})
    assert gen.get("responseMimeType") == "application/json"


async def test_gemini_no_format_no_mime_type():
    """无 response_format 时不应设置 responseMimeType。"""
    captured = {}

    async def fake_post(url, params=None, json=None, headers=None, **k):
        captured["json"] = json
        fr = MagicMock()
        fr.raise_for_status = MagicMock()
        fr.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "plain"}]}}]
        })
        return fr

    with patch("deepeye_mcp.config.settings.gemini_api_key", "k"):
        with patch("deepeye_mcp.config.settings.request_timeout", 5):
            with patch("deepeye_mcp.config.settings.max_retries", 0):
                with patch("deepeye_mcp.vision.gemini_adapter._get_client") as m:
                    m.return_value.post = fake_post
                    adapter = GeminiVisionAdapter(model="gemini-x", api_key="k")
                    await adapter.describe("b64", "image/png", "p")
    gen = captured["json"].get("generationConfig", {})
    assert "responseMimeType" not in gen


# ---------------------------------------------------------------------------
# 声明 5: analyze_images 并发上限
# ---------------------------------------------------------------------------


async def test_analyze_images_concurrency_bounded():
    """大量图片并发峰值不应超过 _ANALYZE_IMAGES_CONCURRENCY。"""
    import asyncio

    active = 0
    peak = 0

    async def slow_describe(*a, **k):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return "x"

    adapter = MagicMock()
    adapter.describe = slow_describe
    adapter.describe_text = AsyncMock(return_value="s")
    with patch("deepeye_mcp.tools.create_vision_adapter", return_value=adapter):
        with patch("deepeye_mcp.tools.preprocess_image", side_effect=lambda b, m: (b, m)):
            with patch("deepeye_mcp.tools.parse_image_source",
                       side_effect=lambda s: (base64.b64encode(b"x").decode(), "image/png")):
                r = await analyze_images(["d1"] * 12)
    from deepeye_mcp.tools import _ANALYZE_IMAGES_CONCURRENCY
    assert peak <= _ANALYZE_IMAGES_CONCURRENCY, f"并发峰值 {peak} > 上限 {_ANALYZE_IMAGES_CONCURRENCY}"
    assert "[1] d1: x" in r[0].text


# ---------------------------------------------------------------------------
# 声明 6: data URI / 本地路径大小上限
# ---------------------------------------------------------------------------


async def test_data_uri_too_large_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_image_bytes", 100)
    big_b64 = base64.b64encode(b"\x00" * 1000).decode()
    with pytest.raises(ValueError, match="大小上限"):
        await parse_image_source(f"data:image/png;base64,{big_b64}")


async def test_local_path_too_large_rejected(monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.setattr(settings, "max_image_bytes", 10)
    p = tmp_path / "big.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with pytest.raises(ValueError, match="大小上限"):
        await parse_image_source(str(p))


# ---------------------------------------------------------------------------
# 声明 7: EXIF 转正
# ---------------------------------------------------------------------------


async def test_exif_rotation_applied(monkeypatch):
    """带 EXIF Orientation=6 (Rotate 90 CW) 的图片应被转正。"""
    import base64 as b64mod
    from PIL import Image

    monkeypatch.setattr(settings, "image_max_dim", 2048)
    img = Image.new("RGB", (100, 50), color=(255, 0, 0))
    exif = img.getexif()
    exif[274] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    b64 = b64mod.b64encode(buf.getvalue()).decode()

    new_b64, _ = preprocess_image(b64, "image/jpeg")
    with Image.open(io.BytesIO(b64mod.b64decode(new_b64))) as out:
        w, h = out.size
    # 转正后应为 50x100（width/height 交换）
    assert (w, h) == (50, 100), f"EXIF 未转正: {out.size}"


# ---------------------------------------------------------------------------
# 声明 8: client 复用
# ---------------------------------------------------------------------------


def test_gemini_uses_module_client():
    """Gemini 适配器应通过 _get_client 复用模块级 client，而非每次新建。"""
    import inspect
    from deepeye_mcp.vision import gemini_adapter
    src = inspect.getsource(gemini_adapter.GeminiVisionAdapter.describe)
    assert "AsyncClient()" not in src, "describe 不应再新建 AsyncClient"
    assert "_get_client()" in src


# ---------------------------------------------------------------------------
# 声明 9: server 层输入校验
# ---------------------------------------------------------------------------


async def test_analyze_layout_invalid_detail_is_error():
    with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
        mf.side_effect = RuntimeError("should not be called")
        r = await call_tool(None, _params(
            _name="analyze_layout", image_source="data:image/png;base64,AAA", detail="garbage"
        ))
    assert r.is_error is True
    assert "detail" in r.content[0].text


async def test_analyze_images_empty_is_error():
    with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
        mf.side_effect = RuntimeError("should not be called")
        r = await call_tool(None, _params(_name="analyze_images", image_sources=[]))
    assert r.is_error is True
    assert "不能为空" in r.content[0].text


async def test_analyze_layout_valid_detail_ok():
    with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
        adapter = MagicMock()
        adapter.describe = AsyncMock(return_value='{"layout_type":"x"}')
        mf.return_value = adapter
        r = await call_tool(None, _params(
            _name="analyze_layout", image_source="data:image/png;base64,AAA", detail="detailed"
        ))
    assert r.is_error is False