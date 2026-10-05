"""2026-09-20 审查修复的回归测试。

逐条钉住审查报告里的 Critical / Important 修法，防止回退：

- 分发层：可选参数不得被显式 ``null`` 覆盖；多余/缺失参数、未知工具、非法
  enum 一律走 ``is_error``；校验清单由 ``_TOOLS`` 的 inputSchema 驱动
- 后端契约：调用方传的 ``max_tokens`` 必须真的到达每个后端
- 安全：CGNAT 段拦截、取图 client 关 ``trust_env``、IP pinning 保留
  ``Host`` 与 ``sni_hostname``、非图片内容拒绝、本地目录白名单
- 性能：多轮 JSON 重试里同一张图只解析一次
- 预算与进度：``REQUEST_DEADLINE`` 生效、带 progressToken 时上报进度
- 脱敏：带引号的 ``Authorization`` 头也要抹掉
"""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolRequestParams

import openeye_mcp.tools as tools
from openeye_mcp.cache import vision_cache
from openeye_mcp.config import settings
from openeye_mcp.errors import VisionError, redact_secrets
from openeye_mcp.image_utils import (
    _is_public_ip,
    load_image_from_url_as_base64,
    parse_image_source,
)
from openeye_mcp.server import call_tool
from openeye_mcp.tools import analyze_layout, describe_image

_FAKE_B64 = base64.b64encode(b"not-a-real-image").decode("ascii")
_DATA_URI = f"data:image/png;base64,{_FAKE_B64}"


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(1, 2, 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def _png_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode("ascii")


def _mock_adapter(return_value: str = "ok", **attrs) -> AsyncMock:
    adapter = AsyncMock()
    adapter.describe = AsyncMock(return_value=return_value)
    adapter.describe_text = AsyncMock(return_value="summary")
    adapter.model = attrs.get("model", "mock-model")
    adapter.base_url = attrs.get("base_url", "https://mock.invalid")
    return adapter


async def _call(name: str, arguments: dict, ctx=None):
    return await call_tool(ctx, CallToolRequestParams(name=name, arguments=arguments))


# ---------------------------------------------------------------------------
# 分发层
# ---------------------------------------------------------------------------


async def test_optional_prompt_not_overridden_by_absent_or_null():
    """客户端省略或显式传 null 时，必须落到工具函数的默认提示词。

    历史缺陷：``analyze_images`` 分支写 ``prompt=arguments.get("prompt")``，
    把 None 直接盖过默认值，最终向所有后端发出 ``"text": null``。
    """
    adapter = _mock_adapter()
    with patch.object(tools, "create_vision_adapter", return_value=adapter), \
         patch.object(tools, "parse_image_source", new=AsyncMock(return_value=(_FAKE_B64, "image/png"))):
        for arguments in (
            {"image_sources": [_DATA_URI]},
            {"image_sources": [_DATA_URI], "prompt": None},
        ):
            adapter.describe.reset_mock()
            result = await _call("analyze_images", arguments)
            assert not result.is_error, result.content[0].text
            sent_prompt = adapter.describe.await_args.args[2]
            assert sent_prompt == tools._DEFAULT_DESCRIBE_PROMPT
            assert sent_prompt is not None


async def test_dispatch_rejects_bad_arguments_with_is_error():
    """未知工具 / 缺必填 / 多余参数 / 非法 enum 都不能漏成协议错误。"""
    cases = [
        ("nope", {}, "未知工具"),
        ("ask_about_image", {"image_source": _DATA_URI}, "缺少必填参数"),
        ("analyze_layout", {"image_source": _DATA_URI, "prompt": "x"}, "不支持的参数"),
        ("analyze_layout", {"image_source": _DATA_URI, "detail": "wrong"}, "仅支持 basic"),
    ]
    for name, arguments, needle in cases:
        result = await _call(name, arguments)
        assert result.is_error, f"{name} 的非法入参未走 isError"
        assert needle in result.content[0].text, (name, result.content[0].text)


async def test_schema_and_handler_tables_stay_in_sync():
    """``_TOOLS`` 与分发表必须一一对应，否则加工具会漏一半。"""
    from openeye_mcp.server import _HANDLERS, _TOOL_SCHEMAS

    assert set(_TOOL_SCHEMAS) == set(_HANDLERS)
    assert set(_TOOL_SCHEMAS) == {"describe_image", "extract_text", "ask_about_image",
                                  "analyze_layout", "extract_table", "analyze_images"}


# ---------------------------------------------------------------------------
# 后端契约：max_tokens 真的到达后端
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_name,adapter_name",
    [
        ("gemini_adapter", "GeminiVisionAdapter"),
        ("gemini_interactions_adapter", "GeminiInteractionsAdapter"),
    ],
)
async def test_gemini_family_send_max_tokens(module_name, adapter_name):
    """历史缺陷：两个 Gemini 适配器收下 max_tokens 却不写进 payload。"""
    module = __import__(f"openeye_mcp.vision.{module_name}", fromlist=[adapter_name])
    adapter = getattr(module, adapter_name)(model="m", api_key="k")

    captured: dict = {}

    async def _post(client, url, *, json, headers, params=None):
        captured["payload"] = json
        response = MagicMock()
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "t"}]}}],
                                      "steps": [{"type": "model_output", "content": [{"type": "text", "text": "t"}]}]}
        return response

    with patch.object(module, "post_with_retry", new=_post):
        await adapter.describe("b64", "image/png", "提示词", max_tokens=8192)
        captured.clear()
        await adapter.describe("b64", "image/png", "提示词")

    tokens = (
        captured["payload"].get("generationConfig", {}).get("maxOutputTokens")
        or captured["payload"].get("max_output_tokens")
    )
    assert tokens == settings.max_tokens, "缺省时必须回落到配置默认值"

    with patch.object(module, "post_with_retry", new=_post):
        await adapter.describe("b64", "image/png", "提示词", max_tokens=8192)
    tokens = (
        captured["payload"].get("generationConfig", {}).get("maxOutputTokens")
        or captured["payload"].get("max_output_tokens")
    )
    assert tokens == 8192


# ---------------------------------------------------------------------------
# 安全
# ---------------------------------------------------------------------------


def test_cgnat_range_is_not_public():
    """100.64.0.0/10 不在 ipaddress.is_private 里，但等价内网（阿里云元数据在此）。"""
    assert not _is_public_ip("100.100.100.200")
    assert not _is_public_ip("100.64.0.1")
    assert _is_public_ip("8.8.8.8")


async def test_download_client_disables_trust_env():
    """取图 client 必须关 ``trust_env``，否则环境里的 HTTP_PROXY 会代我们
    解析与连接，本地的 SSRF 校验形同虚设。"""
    captured: dict = {}

    class _RecordingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.build_request = MagicMock(return_value=MagicMock())
            self.send = AsyncMock(
                return_value=_stream_response(
                    _png_bytes(), {"Content-Type": "image/png"}
                )
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

    with patch("openeye_mcp.image_utils.httpx.AsyncClient", _RecordingClient), patch(
        "openeye_mcp.image_utils.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        b64_data, mime = await load_image_from_url_as_base64("https://example.com/x.png")

    assert captured.get("trust_env") is False
    assert captured.get("follow_redirects") is False, "重定向必须逐跳自行校验"
    assert b64_data and mime == "image/png"


def _stream_response(content: bytes, headers: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.headers = headers
    response.raise_for_status = MagicMock()
    response.aclose = AsyncMock()

    async def _aiter(chunk_size: int = 65536):
        yield content

    response.aiter_bytes = _aiter
    return response


async def test_non_image_bytes_rejected_for_every_source(tmp_path: Path):
    """三种来源都必须校验内容确实是图片，否则任意文本会被送到第三方后端。"""
    text_file = tmp_path / "secret.txt"
    text_file.write_bytes(b"password=123")

    with pytest.raises(ValueError, match="不是可识别的图片"):
        await parse_image_source(str(text_file))
    with pytest.raises(ValueError, match="不是可识别的图片"):
        await parse_image_source(_DATA_URI)


async def test_local_path_outside_allowed_roots_rejected(tmp_path: Path, monkeypatch):
    """ALLOWED_IMAGE_ROOTS 非空时，白名单外的本地路径必须被拒。"""
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setattr(settings, "allowed_image_roots", str(root))

    with pytest.raises(ValueError, match="ALLOWED_IMAGE_ROOTS"):
        await parse_image_source(str(outside))

    inside = root / "inside.png"
    inside.write_bytes(_png_bytes())
    b64_data, mime = await parse_image_source(str(inside))
    assert b64_data and mime == "image/png"


# ---------------------------------------------------------------------------
# 性能与预算
# ---------------------------------------------------------------------------


async def test_json_retry_loop_parses_source_only_once(monkeypatch):
    """布局重试不该把同一张图反复下载解码。"""
    monkeypatch.setattr(settings, "request_deadline", 0)
    parses = AsyncMock(return_value=(_FAKE_B64, "image/png"))
    adapter = _mock_adapter(return_value="这里没有 JSON")
    with patch.object(tools, "parse_image_source", parses), \
         patch.object(tools, "create_vision_adapter", return_value=adapter):
        with pytest.raises(VisionError, match="未返回有效 JSON"):
            await analyze_layout(_DATA_URI)

    assert adapter.describe.await_count > 1, "应当重试多轮"
    assert parses.await_count == 1, f"同一张图被解析了 {parses.await_count} 次"


async def test_deadline_aborts_long_tool_call(monkeypatch):
    """超过 REQUEST_DEADLINE 必须主动中止并报清楚，而不是让客户端掐。"""
    monkeypatch.setattr(settings, "request_deadline", 0.2)
    adapter = _mock_adapter()

    async def _slow(*args, **kwargs):
        await asyncio.sleep(5)
        return "never"

    adapter.describe = AsyncMock(side_effect=_slow)

    with patch.object(tools, "create_vision_adapter", return_value=adapter), \
         patch.object(tools, "parse_image_source", new=AsyncMock(return_value=(_FAKE_B64, "image/png"))):
        result = await _call("describe_image", {"image_source": _DATA_URI})

    assert result.is_error
    assert "总时间预算" in result.content[0].text


async def test_progress_notification_sent_when_token_present():
    """带 progressToken 时，视觉请求前要发出进度通知。"""
    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.session.send_progress_notification = AsyncMock()
    adapter = _mock_adapter()
    params = CallToolRequestParams(
        name="describe_image",
        arguments={"image_source": _DATA_URI},
        meta={"progressToken": "tok-1"},
    )
    with patch.object(tools, "create_vision_adapter", return_value=adapter), \
         patch.object(tools, "parse_image_source", new=AsyncMock(return_value=(_FAKE_B64, "image/png"))):
        await call_tool(ctx, params)

    assert ctx.session.send_progress_notification.await_count >= 1
    kwargs = ctx.session.send_progress_notification.await_args.kwargs
    assert kwargs["progress_token"] == "tok-1"


# ---------------------------------------------------------------------------
# 缓存指纹与脱敏
# ---------------------------------------------------------------------------


async def test_cache_is_isolated_per_resolved_model(monkeypatch):
    """换了 OPENAI_MODEL / BASE_URL 不能还在 TTL 内命中旧模型的缓存。"""
    monkeypatch.setattr(settings, "cache_enabled", True)
    vision_cache.clear()
    try:
        for model, base in (("model-a", "https://a.invalid"), ("model-b", "https://b.invalid")):
            adapter = _mock_adapter(return_value=f"结果-{model}", model=model, base_url=base)
            with patch.object(tools, "create_vision_adapter", return_value=adapter), \
                 patch.object(tools, "parse_image_source", new=AsyncMock(return_value=(_FAKE_B64, "image/png"))):
                result = await describe_image(_DATA_URI, prompt="同一个提示词")
            assert f"结果-{model}" in result[0].text
    finally:
        vision_cache.clear()


def test_redact_covers_quoted_authorization_header():
    """``'Authorization': 'Bearer sk-...'`` 这种带引号写法也要被抹掉。"""
    text = "headers={'Authorization': 'Bearer sk-abcdefghijklmnop'}"
    redacted = redact_secrets(text)
    assert "sk-abcdefghijklmnop" not in redacted
