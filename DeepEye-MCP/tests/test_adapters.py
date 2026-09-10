
"""``GeminiVisionAdapter`` 与 ``OpenAIVisionAdapter`` 单元测试。

通过 ``unittest.mock.patch`` 替换适配器模块内的 ``httpx.AsyncClient``，
避免任何真实 API 调用；验证 payload 构造、URL、返回值解析与错误处理。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deepeye_mcp.config import settings
from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter
from deepeye_mcp.vision.openai_adapter import OpenAIVisionAdapter


# ---------------------------------------------------------------------------
# 辅助：构造 fake httpx.AsyncClient
# ---------------------------------------------------------------------------


def _make_fake_client(json_payload: dict, status_code: int = 200) -> AsyncMock:
    """构造一个 fake ``httpx.AsyncClient``，POST 返回指定 JSON。"""
    fake_response = MagicMock()
    fake_response.json.return_value = json_payload
    fake_response.status_code = status_code
    fake_response.raise_for_status = MagicMock()

    fake_client = AsyncMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    return fake_client


def _make_error_client(response: MagicMock) -> AsyncMock:
    """构造 fake client，其响应 ``raise_for_status`` 抛 HTTPStatusError。"""
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Internal Server Error",
        request=MagicMock(),
        response=response,
    )
    fake_client = AsyncMock()
    fake_client.post = AsyncMock(return_value=response)
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    return fake_client


# ---------------------------------------------------------------------------
# GeminiVisionAdapter
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.vision.gemini_adapter._get_client")
async def test_gemini_describe_returns_text(mock_client_cls):
    """describe 应返回 candidates[0].content.parts[0].text（去空白）。"""
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "  一只橘猫坐在窗台上  "}]}}
        ]
    }
    mock_client_cls.return_value = _make_fake_client(payload)

    adapter = GeminiVisionAdapter(
        model="gemini-1.5-pro",
        api_key="fake-key",
    )
    text = await adapter.describe("iVBOR", "image/png", "描述图片")

    assert text == "一只橘猫坐在窗台上"


@patch("deepeye_mcp.vision.gemini_adapter._get_client")
async def test_gemini_describe_payload_and_url(mock_client_cls):
    """验证 URL 拼接、query 参数与 payload 结构。"""
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}]}}
        ]
    }
    fake_client = _make_fake_client(payload)
    mock_client_cls.return_value = fake_client

    adapter = GeminiVisionAdapter(
        model="gemini-2.0-flash",
        api_key="my-api-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    await adapter.describe("iVBOR==", "image/png", "描述这张图")

    fake_client.post.assert_awaited_once()
    call = fake_client.post.await_args

    url = call.args[0]
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-2.0-flash:generateContent"
    )

    # query 参数 ?key=...
    params = call.kwargs.get("params")
    assert params == {"key": "my-api-key"}

    # payload 结构
    sent_payload = call.kwargs.get("json")
    assert sent_payload == {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": "image/png", "data": "iVBOR=="}},
                    {"text": "描述这张图"},
                ]
            }
        ]
    }


@patch("deepeye_mcp.vision.gemini_adapter._get_client")
async def test_gemini_describe_raises_on_error_status(mock_client_cls):
    """非 2xx 响应应通过 raise_for_status 抛 HTTPStatusError。"""
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_client = _make_error_client(fake_response)
    mock_client_cls.return_value = fake_client

    adapter = GeminiVisionAdapter(model="gemini-1.5-pro", api_key="k")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.describe("iVBOR", "image/png", "prompt")


def test_gemini_default_base_url():
    """未传 base_url 时应回退到官方端点。"""
    adapter = GeminiVisionAdapter(model="gemini-1.5-pro", api_key="k")
    assert (
        adapter.base_url
        == "https://generativelanguage.googleapis.com/v1beta"
    )


def test_gemini_reads_settings_defaults(monkeypatch):
    """未传参时应从 settings 读取 gemini_model / gemini_api_key。"""
    monkeypatch.setattr(settings, "gemini_model", "gemini-1.5-pro")
    monkeypatch.setattr(settings, "gemini_api_key", "from-settings-key")
    adapter = GeminiVisionAdapter()
    assert adapter.model == "gemini-1.5-pro"
    assert adapter.api_key == "from-settings-key"


# ---------------------------------------------------------------------------
# describe_text（纯文本请求）
# ---------------------------------------------------------------------------


@patch("deepeye_mcp.vision.gemini_adapter._get_client")
async def test_gemini_describe_text(mock_get_client):
    """Gemini describe_text 走 generateContent，parts 仅含 text。"""
    payload = {"candidates": [{"content": {"parts": [{"text": "summary"}]}}]}
    fake_client = _make_fake_client(payload)
    mock_get_client.return_value = fake_client

    adapter = GeminiVisionAdapter(model="gemini-2.0-flash", api_key="k")
    text = await adapter.describe_text("请总结")

    assert text == "summary"
    call = fake_client.post.await_args
    sent = call.kwargs["json"]
    assert sent["contents"][0]["parts"][0]["text"] == "请总结"
    assert "inline_data" not in str(sent["contents"])


# ---------------------------------------------------------------------------
# OpenAIVisionAdapter（病态响应防御）
# ---------------------------------------------------------------------------


def _make_openai_client(payload: dict) -> AsyncMock:
    """构造 fake ``AsyncClient``，验证 openai adapter 的模块级单例调用。"""
    fake_response = MagicMock()
    fake_response.json.return_value = payload
    fake_response.raise_for_status = MagicMock()
    fake_client = AsyncMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    return fake_client


@patch("deepeye_mcp.vision.openai_adapter._get_client")
async def test_openai_describe_choices_null_degraded(mock_get_client):
    """choices 为 None 时应返回空串而不是抛 TypeError。"""
    mock_get_client.return_value = _make_openai_client({"choices": None})

    adapter = OpenAIVisionAdapter(
        model="step-3.7-flash",
        api_key="k",
        base_url="https://example.com/v1",
    )
    text = await adapter.describe("iVBOR", "image/png", "prompt")

    assert text == ""


@patch("deepeye_mcp.vision.openai_adapter._get_client")
async def test_openai_describe_choices_empty_array_degraded(mock_get_client):
    """choices 为空数组时应返回空串而不是抛 IndexError。"""
    mock_get_client.return_value = _make_openai_client({"choices": []})

    adapter = OpenAIVisionAdapter(
        model="step-3.7-flash",
        api_key="k",
        base_url="https://example.com/v1",
    )
    text = await adapter.describe("iVBOR", "image/png", "prompt")

    assert text == ""


@patch("deepeye_mcp.vision.openai_adapter._get_client")
async def test_openai_describe_text_choices_null_degraded(mock_get_client):
    """describe_text 遇到 choices=None 时返回空串而不是抛异常。"""
    mock_get_client.return_value = _make_openai_client({"choices": None})

    adapter = OpenAIVisionAdapter(
        model="step-3.7-flash",
        api_key="k",
        base_url="https://example.com/v1",
    )
    text = await adapter.describe_text("请总结")

    assert text == ""
