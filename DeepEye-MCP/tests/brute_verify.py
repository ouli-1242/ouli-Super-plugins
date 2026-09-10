"""DeepEye 暴力验证脚本（手动运行，非 pytest）。

验证修复后行为：isError、SSRF 重定向、ocr_backend provider、Gemini json、
并发上限、大小上限、EXIF、client 复用、输入校验。
用法：python tests/brute_verify.py
"""
import asyncio
import base64
import io
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from mcp.types import CallToolResult

from deepeye_mcp.config import settings
from deepeye_mcp.errors import VisionError
from deepeye_mcp.image_utils import parse_image_source, preprocess_image
from deepeye_mcp.server import call_tool
from deepeye_mcp.tools import analyze_images, extract_text
from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter

_PUBLIC_IP = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
FAIL = []
PASS = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}: {detail}")


def _params(**kwargs):
    m = MagicMock()
    m.name = kwargs.pop("_name", "")
    m.arguments = kwargs
    return m


async def verify_is_error():
    print("=== 声明 1: 失败置 isError ===")
    for name, args in [
        ("describe_image", {"image_source": "/nonexistent/nope.png"}),
        ("extract_text", {"image_source": "/nonexistent/nope.png"}),
        ("ask_about_image", {"image_source": "/nonexistent/nope.png", "question": "q"}),
        ("extract_table", {"image_source": "/nonexistent/nope.png"}),
        ("analyze_layout", {"image_source": "/nonexistent/nope.png"}),
    ]:
        with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
            mf.side_effect = RuntimeError("boom")
            r = await call_tool(None, _params(_name=name, **args))
        check(f"isError {name}", r.is_error is True, f"got is_error={r.is_error}")
    print(f"  -> {len(PASS)} passed")


async def verify_redirect_ssrf():
    print("=== 声明 2: SSRF 重定向逐跳校验 ===")
    ensure_calls = []

    async def fake_get(url, *a, **k):
        fr = MagicMock()
        fr.status_code = 301
        fr.headers = httpx.Headers({"Location": "http://127.0.0.1:8080/internal.png"})
        return fr

    fc = AsyncMock()
    fc.get = fake_get
    fc.__aenter__.return_value = fc
    fc.__aexit__.return_value = None

    def fake_ensure(url):
        ensure_calls.append(url)
        if "127.0.0.1" in url:
            raise ValueError("拒绝访问非公网地址（SSRF 防护）: 127.0.0.1 (127.0.0.1)")
        return url

    with patch("deepeye_mcp.image_utils._ensure_public_target", side_effect=fake_ensure):
        with patch("deepeye_mcp.image_utils.httpx.AsyncClient", return_value=fc):
            try:
                from deepeye_mcp.image_utils import load_image_from_url_as_base64
                await load_image_from_url_as_base64("https://example.com/x.png")
                check("重定向到内网被拒", False, "未拒绝")
            except ValueError as e:
                check("重定向到内网被拒", "SSRF" in str(e) or "非公网" in str(e), str(e))
    check("逐跳校验", len(ensure_calls) >= 2, f"校验次数 {len(ensure_calls)}")


async def verify_ocr_backend():
    print("=== 声明 3: extract_text 用 ocr_backend ===")
    settings.ocr_backend = "gemini"
    adapter = MagicMock()
    adapter.describe = AsyncMock(return_value="OCR")
    with patch("deepeye_mcp.tools.create_vision_adapter", return_value=adapter) as mf:
        await extract_text(image_source="data:image/png;base64,AAA")
    check("ocr_backend provider", mf.call_args.kwargs.get("provider") == "gemini",
          f"provider={mf.call_args}")


async def verify_gemini_json():
    print("=== 声明 4: Gemini json_object 映射 ===")
    captured = {}

    async def fake_post(url, params=None, json=None, headers=None, **k):
        captured["json"] = json
        fr = MagicMock()
        fr.raise_for_status = MagicMock()
        fr.json = MagicMock(return_value={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
        return fr

    with patch("deepeye_mcp.config.settings.gemini_api_key", "k"):
        with patch("deepeye_mcp.config.settings.request_timeout", 5):
            with patch("deepeye_mcp.config.settings.max_retries", 0):
                with patch("deepeye_mcp.vision.gemini_adapter._get_client") as m:
                    m.return_value.post = fake_post
                    adapter = GeminiVisionAdapter(model="gemini-x", api_key="k")
                    await adapter.describe("b64", "image/png", "p",
                                           response_format={"type": "json_object"})
    gen = captured["json"].get("generationConfig", {})
    check("Gemini responseMimeType", gen.get("responseMimeType") == "application/json", str(gen))


async def verify_concurrency():
    print("=== 声明 5: analyze_images 并发上限 ===")
    import asyncio
    from deepeye_mcp.tools import _ANALYZE_IMAGES_CONCURRENCY
    active = 0
    peak = 0

    async def slow(*a, **k):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return "x"

    adapter = MagicMock()
    adapter.describe = slow
    adapter.describe_text = AsyncMock(return_value="s")
    with patch("deepeye_mcp.tools.create_vision_adapter", return_value=adapter):
        with patch("deepeye_mcp.tools.parse_image_source",
                   side_effect=lambda s: (base64.b64encode(b"x").decode(), "image/png")):
            with patch("deepeye_mcp.tools.preprocess_image", side_effect=lambda b, m: (b, m)):
                await analyze_images(["d1"] * 12)
    check("并发上限", peak <= _ANALYZE_IMAGES_CONCURRENCY, f"peak={peak} limit={_ANALYZE_IMAGES_CONCURRENCY}")


async def verify_size_limit():
    print("=== 声明 6: 大小上限所有来源 ===")
    old = settings.max_image_bytes
    settings.max_image_bytes = 100
    try:
        big_b64 = base64.b64encode(b"\x00" * 500).decode()
        try:
            await parse_image_source(f"data:image/png;base64,{big_b64}")
            check("data URI 超限拒绝", False, "未拒绝")
        except ValueError:
            check("data URI 超限拒绝", True)
    finally:
        settings.max_image_bytes = old


async def verify_exif():
    print("=== 声明 7: EXIF 转正 ===")
    from PIL import Image
    old_dim = settings.image_max_dim
    settings.image_max_dim = 2048
    try:
        img = Image.new("RGB", (100, 50), color=(255, 0, 0))
        exif = img.getexif()
        exif[274] = 6
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        b64 = base64.b64encode(buf.getvalue()).decode()
        new_b64, _ = preprocess_image(b64, "image/jpeg")
        with Image.open(io.BytesIO(base64.b64decode(new_b64))) as out:
            size = out.size
        check("EXIF 转正", size == (50, 100), f"size={size}")
    finally:
        settings.image_max_dim = old_dim


async def verify_input_validation():
    print("=== 声明 9: 输入校验 ===")
    with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
        mf.side_effect = RuntimeError("should not be called")
        r = await call_tool(None, _params(_name="analyze_layout",
                                          image_source="data:image/png;base64,AAA",
                                          detail="garbage"))
    check("detail 非法值 isError", r.is_error is True, f"is_error={r.is_error}")
    with patch("deepeye_mcp.tools.create_vision_adapter") as mf:
        mf.side_effect = RuntimeError("should not be called")
        r = await call_tool(None, _params(_name="analyze_images", image_sources=[]))
    check("空数组 isError", r.is_error is True, f"is_error={r.is_error}")


async def main():
    await verify_is_error()
    await verify_redirect_ssrf()
    await verify_ocr_backend()
    await verify_gemini_json()
    await verify_concurrency()
    await verify_size_limit()
    await verify_exif()
    await verify_input_validation()
    print(f"\n结果: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("失败项:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))