"""错误消息脱敏回归测试。

复现历史缺陷：Gemini 后端把 API Key 放在 URL query（``?key=...``），
``httpx.HTTPStatusError`` 的文本包含完整 URL，经 :func:`classify_error`
原样拼进返回值后，会回显到 MCP 工具输出（agent context）与日志。
"""

from __future__ import annotations

import httpx
import pytest

from deepeye_mcp.errors import VisionError, classify_error


def _status_error(url: str, status: int = 401) -> httpx.HTTPStatusError:
    """构造与 httpx 真实行为一致的 HTTPStatusError（消息含完整 URL）。"""
    request = httpx.Request("POST", url)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"Client error '{status}' for url '{url}'",
        request=request,
        response=response,
    )


def test_status_error_message_redacts_query_key():
    """URL query 中的 key 不得出现在分类结果里。"""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro"
        ":generateContent?key=SUPER-SECRET-KEY"
    )
    category, message = classify_error(_status_error(url))

    assert category == "backend"
    assert "SUPER-SECRET-KEY" not in message
    assert "***" in message


def test_status_error_message_redacts_interactions_query_key():
    """Interactions 端点同样走 ?key=，也必须脱敏。"""
    url = "https://generativelanguage.googleapis.com/v1beta/interactions?key=ANOTHER-SECRET"
    _, message = classify_error(_status_error(url, status=400))

    assert "ANOTHER-SECRET" not in message


def test_message_redacts_bearer_token():
    """RuntimeError 文案里的 Bearer token 必须脱敏。"""
    exc = RuntimeError("网络传输错误：Bearer sk-abcdef1234567890。建议检查网络")

    _, message = classify_error(exc)

    assert "sk-abcdef1234567890" not in message


def test_message_redacts_api_key_parameter():
    """形如 api_key=xxx 的片段必须脱敏。"""
    exc = RuntimeError("网络传输错误：请求失败 api_key=SEKRET-VALUE&page=1")

    _, message = classify_error(exc)

    assert "SEKRET-VALUE" not in message


def test_message_redacts_header_style_key():
    """形如 x-api-key: xxx 的片段必须脱敏。"""
    exc = RuntimeError("网络传输错误：headers {'x-api-key': 'HEADER-SECRET'}")

    _, message = classify_error(exc)

    assert "HEADER-SECRET" not in message


def test_redaction_keeps_message_readable():
    """脱敏不应把整条消息清空——非敏感部分必须保留。"""
    url = "https://example.com/v1/models?key=SECRET&alt=sse"
    _, message = classify_error(_status_error(url))

    assert "example.com" in message


def test_provider_is_used_in_backend_message(monkeypatch):
    """provider 参数应出现在后端错误文案里，便于定位是哪一路后端。"""
    url = "https://example.com/v1/models?key=k"
    _, message = classify_error(_status_error(url, status=503), provider="gemini")

    assert "gemini" in message


def test_provider_omitted_when_empty():
    """未传 provider 时不应出现多余的后端标记。"""
    url = "https://example.com/v1/models?key=k"
    _, message = classify_error(_status_error(url, status=503))

    assert "后端（" not in message


def test_vision_error_is_not_reclassified():
    """VisionError 自带文案，classify_error 只做兜底。"""
    category, message = classify_error(VisionError("布局分析失败：模型多次未返回有效 JSON"))

    assert category == "unknown"
    assert "布局分析失败" in message


@pytest.mark.parametrize(
    "message",
    [
        "URL 缺少主机名",
        "无法解析主机: example.com",
        "重定向缺少 Location 头: https://example.com/a",
        "重定向次数超过上限: 5",
        "data URI 不含 base64 数据",
        "拒绝访问非公网地址（SSRF 防护）: example.com (10.0.0.1)",
    ],
)
def test_image_source_errors_classified_as_image(message):
    """image_utils 的所有来源错误都应归入 image，而非 unknown。"""
    from deepeye_mcp.errors import ImageSourceError

    category, _ = classify_error(ImageSourceError(message))

    assert category == "image"
