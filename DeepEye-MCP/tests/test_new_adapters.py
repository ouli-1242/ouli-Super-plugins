"""Anthropic + Responses 适配器单元测试。

验证协议差异：认证头、图片 block、响应解析、JSON 结构化输出映射。
全部 mock，无真实 API 调用。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deepeye_mcp.config import settings
from deepeye_mcp.vision.anthropic_adapter import AnthropicVisionAdapter
from deepeye_mcp.vision.responses_adapter import ResponsesVisionAdapter


def _fake_response(json_payload: dict, status: int = 200) -> MagicMock:
    fr = MagicMock()
    fr.json.return_value = json_payload
    fr.status_code = status
    fr.text = ""
    fr.raise_for_status = MagicMock()
    return fr


# ─── Anthropic ───────────────────────────────────────────────────────────────


@patch("deepeye_mcp.vision.anthropic_adapter._get_client")
async def test_anthropic_payload_and_auth(mock_get_client):
    """验证 x-api-key 认证 + image block + 图片在文本前。"""
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _fake_response({"content": [{"type": "text", "text": "ok"}]})

    mock_get_client.return_value.post = fake_post

    adapter = AnthropicVisionAdapter(
        model="claude-sonnet-5", api_key="ak-test", base_url="https://api.anthropic.com/v1"
    )
    text = await adapter.describe("iVBOR", "image/png", "描述图片")

    assert text == "ok"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    # 认证头
    assert captured["headers"]["x-api-key"] == "ak-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    # 请求体
    body = captured["json"]
    assert body["model"] == "claude-sonnet-5"
    assert "max_tokens" in body  # 必填
    msg = body["messages"][0]
    assert msg["role"] == "user"
    # 图片 block 在文本之前
    assert msg["content"][0]["type"] == "image"
    assert msg["content"][0]["source"]["media_type"] == "image/png"
    assert msg["content"][1] == {"type": "text", "text": "描述图片"}


@patch("deepeye_mcp.vision.anthropic_adapter._get_client")
async def test_anthropic_skips_thinking_blocks(mock_get_client):
    """响应含 thinking 块时应跳过，只取 text 块。"""
    content = [
        {"type": "thinking", "thinking": "思考过程"},
        {"type": "text", "text": "结果一"},
        {"type": "text", "text": "结果二"},
        {"type": "tool_use", "id": "x", "name": "f", "input": {}},
    ]
    mock_get_client.return_value.post = AsyncMock(
        return_value=_fake_response({"content": content})
    )
    adapter = AnthropicVisionAdapter(model="claude-sonnet-5", api_key="k")
    text = await adapter.describe("iVBOR", "image/png", "p")
    assert text == "结果一\n结果二"


@patch("deepeye_mcp.vision.anthropic_adapter._get_client")
async def test_anthropic_json_object_maps_output_config(mock_get_client):
    """json_object 应映射为 output_config.format（json_schema）。"""
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["json"] = json
        return _fake_response({"content": [{"type": "text", "text": "{}"}]})

    mock_get_client.return_value.post = fake_post
    adapter = AnthropicVisionAdapter(model="claude-sonnet-5", api_key="k")
    await adapter.describe("iVBOR", "image/png", "p",
                           response_format={"type": "json_object"})
    oc = captured["json"].get("output_config", {})
    assert oc.get("format", {}).get("type") == "json_schema"
    assert oc["format"]["strict"] is True


@patch("deepeye_mcp.vision.anthropic_adapter._get_client")
async def test_anthropic_effort_maps_to_output_config(mock_get_client):
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["json"] = json
        return _fake_response({"content": [{"type": "text", "text": "x"}]})

    mock_get_client.return_value.post = fake_post
    adapter = AnthropicVisionAdapter(model="claude-sonnet-5", api_key="k")
    await adapter.describe("iVBOR", "image/png", "p", reasoning_effort="low")
    assert captured["json"]["output_config"]["effort"] == "low"


@patch("deepeye_mcp.vision.anthropic_adapter._get_client")
async def test_anthropic_raises_on_error_status(mock_get_client):
    fr = MagicMock()
    fr.status_code = 429
    fr.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=MagicMock(), response=fr)
    mock_get_client.return_value.post = AsyncMock(return_value=fr)
    adapter = AnthropicVisionAdapter(model="c", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.describe("iVBOR", "image/png", "p")


async def test_anthropic_defaults_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_model", "claude-haiku-4-5")
    monkeypatch.setattr(settings, "anthropic_api_key", "cfg-key")
    adapter = AnthropicVisionAdapter()
    assert adapter.model == "claude-haiku-4-5"
    assert adapter.api_key == "cfg-key"


# ─── Responses ───────────────────────────────────────────────────────────────


@patch("deepeye_mcp.vision.responses_adapter._get_client")
async def test_responses_payload_and_auth(mock_get_client):
    """验证 Bearer 认证 + input_image 块 + input 数组结构。"""
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _fake_response({"output": [
            {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}
        ]})

    mock_get_client.return_value.post = fake_post

    adapter = ResponsesVisionAdapter(
        model="gpt-5.6", api_key="sk-test", base_url="https://api.openai.com/v1"
    )
    text = await adapter.describe("iVBOR", "image/png", "描述图片")

    assert text == "ok"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    body = captured["json"]
    assert body["model"] == "gpt-5.6"
    assert "max_output_tokens" in body
    # input 数组：图片在前，文本在后
    assert body["input"][0]["type"] == "input_image"
    assert body["input"][0]["image_url"].startswith("data:image/png;base64,")
    assert body["input"][1]["type"] == "message"
    assert body["input"][1]["content"][0]["type"] == "input_text"


@patch("deepeye_mcp.vision.responses_adapter._get_client")
async def test_responses_skips_non_message_items(mock_get_client):
    """output 含 reasoning/function_call 时应跳过，只取 message 的 output_text。"""
    output = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "思考"}]},
        {"type": "message", "content": [{"type": "output_text", "text": "最终答案"}]},
        {"type": "function_call", "name": "f", "arguments": "{}"},
    ]
    mock_get_client.return_value.post = AsyncMock(return_value=_fake_response({"output": output}))
    adapter = ResponsesVisionAdapter(model="gpt-5.6", api_key="k")
    text = await adapter.describe("iVBOR", "image/png", "p")
    assert text == "最终答案"


@patch("deepeye_mcp.vision.responses_adapter._get_client")
async def test_responses_json_object_maps_text_format(mock_get_client):
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["json"] = json
        return _fake_response({"output": [
            {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}
        ]})

    mock_get_client.return_value.post = fake_post
    adapter = ResponsesVisionAdapter(model="gpt-5.6", api_key="k")
    await adapter.describe("iVBOR", "image/png", "p",
                           response_format={"type": "json_object"})
    fmt = captured["json"].get("text", {}).get("format", {})
    assert fmt.get("type") == "json_schema"
    assert fmt["strict"] is True


@patch("deepeye_mcp.vision.responses_adapter._get_client")
async def test_responses_effort_maps_to_reasoning(mock_get_client):
    captured = {}

    async def fake_post(url, json=None, headers=None, **k):
        captured["json"] = json
        return _fake_response({"output": [
            {"type": "message", "content": [{"type": "output_text", "text": "x"}]}
        ]})

    mock_get_client.return_value.post = fake_post
    adapter = ResponsesVisionAdapter(model="gpt-5.6", api_key="k")
    await adapter.describe("iVBOR", "image/png", "p", reasoning_effort="medium")
    assert captured["json"]["reasoning"]["effort"] == "medium"


@patch("deepeye_mcp.vision.responses_adapter._get_client")
async def test_responses_raises_on_error_status(mock_get_client):
    fr = MagicMock()
    fr.status_code = 400
    fr.raise_for_status.side_effect = httpx.HTTPStatusError("400", request=MagicMock(), response=fr)
    mock_get_client.return_value.post = AsyncMock(return_value=fr)
    adapter = ResponsesVisionAdapter(model="gpt-5.6", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.describe("iVBOR", "image/png", "p")


async def test_responses_defaults_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "responses_model", "gpt-5.6")
    monkeypatch.setattr(settings, "responses_api_key", "cfg-key")
    adapter = ResponsesVisionAdapter()
    assert adapter.model == "gpt-5.6"
    assert adapter.api_key == "cfg-key"


async def test_factory_registers_new_providers(monkeypatch):
    """工厂能创建 anthropic + responses。"""
    from deepeye_mcp.vision import create_vision_adapter
    monkeypatch.setattr(settings, "vision_provider", "anthropic")
    a = create_vision_adapter()
    assert isinstance(a, AnthropicVisionAdapter)
    monkeypatch.setattr(settings, "vision_provider", "responses")
    r = create_vision_adapter()
    assert isinstance(r, ResponsesVisionAdapter)

# ─── Gemini Interactions ─────────────────────────────────────────────────────


@patch("deepeye_mcp.vision.gemini_interactions_adapter._get_client")
async def test_interactions_payload_and_store_false(mock_get_client):
    """验证 input 数组 + image block + store=false。"""
    from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
    captured = {}

    async def fake_post(url, params=None, json=None, headers=None, **k):
        captured["url"] = url
        captured["json"] = json
        captured["params"] = params
        return _fake_response({"steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "ok"}]}
        ]})

    mock_get_client.return_value.post = fake_post

    adapter = GeminiInteractionsAdapter(model="gemini-3.6-flash", api_key="gk")
    text = await adapter.describe("iVBOR", "image/png", "描述图片")

    assert text == "ok"
    assert captured["url"].endswith("/interactions")
    assert captured["params"]["key"] == "gk"
    body = captured["json"]
    assert body["model"] == "gemini-3.6-flash"
    assert body["store"] is False  # 临时图片不留存
    # input 数组：图片在前，文本在后
    assert body["input"][0]["type"] == "image"
    assert body["input"][0]["data"] == "iVBOR"
    assert body["input"][0]["mime_type"] == "image/png"
    assert body["input"][1] == {"type": "text", "text": "描述图片"}


@patch("deepeye_mcp.vision.gemini_interactions_adapter._get_client")
async def test_interactions_skips_non_model_output_steps(mock_get_client):
    """steps 含 user_input/function_call 时应跳过，只取 model_output 文本。"""
    from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
    steps = [
        {"type": "user_input", "content": [{"type": "text", "text": "问题"}]},
        {"type": "model_output", "content": [{"type": "text", "text": "答案A"}, {"type": "text", "text": "答案B"}]},
        {"type": "function_call", "name": "f", "args": "{}"},
    ]
    mock_get_client.return_value.post = AsyncMock(return_value=_fake_response({"steps": steps}))
    adapter = GeminiInteractionsAdapter(model="gemini-3.6-flash", api_key="k")
    text = await adapter.describe("iVBOR", "image/png", "p")
    assert text == "答案A\n答案B"


@patch("deepeye_mcp.vision.gemini_interactions_adapter._get_client")
async def test_interactions_json_object_maps_response_format(mock_get_client):
    """json_object 应映射为顶层 response_format 数组。"""
    from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
    captured = {}

    async def fake_post(url, params=None, json=None, headers=None, **k):
        captured["json"] = json
        return _fake_response({"steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "{}"}]}
        ]})

    mock_get_client.return_value.post = fake_post
    adapter = GeminiInteractionsAdapter(model="gemini-3.6-flash", api_key="k")
    await adapter.describe("iVBOR", "image/png", "p",
                           response_format={"type": "json_object"})
    fmt = captured["json"].get("response_format", [])
    assert fmt and fmt[0].get("mime_type") == "application/json"


@patch("deepeye_mcp.vision.gemini_interactions_adapter._get_client")
async def test_interactions_raises_on_error_status(mock_get_client):
    from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
    fr = MagicMock()
    fr.status_code = 400
    fr.raise_for_status.side_effect = httpx.HTTPStatusError("400", request=MagicMock(), response=fr)
    mock_get_client.return_value.post = AsyncMock(return_value=fr)
    adapter = GeminiInteractionsAdapter(model="gemini-3.6-flash", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.describe("iVBOR", "image/png", "p")


async def test_factory_registers_interactions(monkeypatch):
    """工厂能创建 gemini-interactions。"""
    from deepeye_mcp.vision import create_vision_adapter
    from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
    monkeypatch.setattr(settings, "vision_provider", "gemini-interactions")
    a = create_vision_adapter()
    assert isinstance(a, GeminiInteractionsAdapter)
