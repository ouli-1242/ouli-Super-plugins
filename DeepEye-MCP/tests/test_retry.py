"""``deepeye_mcp.vision._retry.post_with_retry`` 单元测试。

历史缺陷：五个适配器各自复制了一份重试循环，且只捕获
Timeout/Transport——429 限流与 5xx 故障不重试，与错误文案
「请稍后重试」自相矛盾。这里验证统一后的重试语义。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deepeye_mcp.config import settings
from deepeye_mcp.vision._retry import post_with_retry


def _response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=response
        )
    return response


def _client(status_codes: list[int]) -> AsyncMock:
    """返回按顺序给出各次响应的 fake client。"""
    client = AsyncMock()
    queue = [_response(code) for code in status_codes]

    async def _post(url, json=None, headers=None, params=None):
        return queue.pop(0)

    client.post = _post
    return client


async def _call(client: AsyncMock):
    return await post_with_retry(
        client, "https://example.com/v1", json={}, headers={}
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_retryable_statuses_are_retried(status, monkeypatch):
    """429 与 5xx 应重试；重试成功时返回响应。"""
    monkeypatch.setattr(settings, "max_retries", 2)
    client = _client([status, status, 200])

    response = await _call(client)

    assert response.status_code == 200


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_client_errors_are_not_retried(status, monkeypatch):
    """4xx（429 除外）重试无意义，应立即抛出，不浪费配额。"""
    monkeypatch.setattr(settings, "max_retries", 3)
    client = _client([status])

    with pytest.raises(httpx.HTTPStatusError):
        await _call(client)


async def test_retry_exhausted_raises_last_exception(monkeypatch):
    """重试用尽后应抛出最后一次失败异常（保留类型供分类）。"""
    monkeypatch.setattr(settings, "max_retries", 2)
    client = _client([503, 503, 503])

    with pytest.raises(httpx.HTTPStatusError):
        await _call(client)


async def test_transport_error_is_retried(monkeypatch):
    """网络传输错误应重试。"""
    monkeypatch.setattr(settings, "max_retries", 1)
    calls = {"n": 0}

    async def _post(url, json=None, headers=None, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=MagicMock())
        return _response(200)

    client = AsyncMock()
    client.post = _post

    response = await _call(client)

    assert response.status_code == 200
    assert calls["n"] == 2


async def test_timeout_is_retried(monkeypatch):
    """超时应重试。"""
    monkeypatch.setattr(settings, "max_retries", 1)

    async def _post(url, json=None, headers=None, params=None):
        raise httpx.ReadTimeout("slow", request=MagicMock())

    client = AsyncMock()
    client.post = _post

    with pytest.raises(httpx.TimeoutException):
        await _call(client)


async def test_backoff_is_applied_and_doubles(monkeypatch):
    """退避时长应为 retry_backoff * 2**(n-1)，且可被配置关闭。"""
    monkeypatch.setattr(settings, "max_retries", 3)
    monkeypatch.setattr(settings, "retry_backoff", 0.5)
    slept: list[float] = []

    async def _sleep(seconds):
        slept.append(seconds)

    client = _client([503, 503, 503, 503])
    with patch("deepeye_mcp.vision._retry.asyncio.sleep", _sleep):
        with pytest.raises(httpx.HTTPStatusError):
            await _call(client)

    assert slept == [0.5, 1.0, 2.0]


async def test_zero_backoff_skips_sleep(monkeypatch):
    """retry_backoff=0 时不调用 sleep（测试套件依赖该行为保持快速）。"""
    monkeypatch.setattr(settings, "max_retries", 1)
    monkeypatch.setattr(settings, "retry_backoff", 0.0)
    sleep = AsyncMock()

    client = _client([503, 503])
    with patch("deepeye_mcp.vision._retry.asyncio.sleep", sleep):
        with pytest.raises(httpx.HTTPStatusError):
            await _call(client)

    sleep.assert_not_called()


async def test_params_are_forwarded(monkeypatch):
    """Gemini 系列依赖 query 参数，必须原样转发。"""
    monkeypatch.setattr(settings, "max_retries", 0)
    captured = {}

    async def _post(url, json=None, headers=None, params=None):
        captured["params"] = params
        return _response(200)

    client = AsyncMock()
    client.post = _post

    await post_with_retry(
        client,
        "https://example.com/v1",
        json={"a": 1},
        headers={"H": "v"},
        params={"key": "k"},
    )

    assert captured["params"] == {"key": "k"}
