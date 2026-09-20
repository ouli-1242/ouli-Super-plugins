"""视觉后端共用的 HTTP POST 重试。

- **重试**：``TimeoutException`` / ``TransportError`` / 429 / 5xx
- **不重试**：其余 4xx（400 / 401 / 403 / 404…）——重试无意义且白耗配额
- **退避**：``retry_backoff * 2**attempt`` 叠加 ±25% 抖动；429 / 5xx 优先
  尊重服务端 ``Retry-After``。纯指数无抖动时，多路并发同时被限流会
  在相同时刻齐发重试（惊群），把 429 持续下去。
- **预算**：睡过头就白等——退避前先确认 :mod:`openeye_mcp.budget`
  的剩余时间还够，不够则立即放弃并已拿到的结果交由上层处理。
- **耗尽**：抛出最后一次异常并保留原始类型，交由
  :func:`openeye_mcp.errors.classify_error` 统一分类。
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from loguru import logger

from openeye_mcp.budget import has_budget_for
from openeye_mcp.config import settings
from openeye_mcp.progress import report

# 服务端要求的最长等待；超过就不如把失败如实报给 agent
_MAX_RETRY_AFTER = 120.0


def _retry_after_seconds(exc: httpx.HTTPStatusError) -> float:
    """解析 ``Retry-After``（秒数或 HTTP-date）；缺失/非法返回 0。"""
    raw = exc.response.headers.get("Retry-After")
    if not isinstance(raw, str) or not raw.strip():
        return 0.0
    raw = raw.strip()
    try:
        seconds = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return 0.0
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - datetime.now(UTC)).total_seconds()
    return min(max(0.0, seconds), _MAX_RETRY_AFTER)


def _backoff(attempt: int) -> float:
    """第 ``attempt`` 次重试的指数退避秒数（含抖动）。"""
    base = settings.retry_backoff * (2**attempt)
    if base <= 0:
        return 0.0
    return base * random.uniform(0.75, 1.25)


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: dict,
    headers: dict,
    params: dict | None = None,
) -> httpx.Response:
    """带退避重试的 POST，返回已通过 ``raise_for_status()`` 的响应。

    Args:
        client: 复用的 ``httpx.AsyncClient``。
        url: 请求地址。
        json: 请求体。
        headers: 请求头。
        params: 查询参数（Gemini 系列需要）。

    Returns:
        状态码为 2xx 的响应。

    Raises:
        最后一次失败的异常：``httpx.TimeoutException``、
        ``httpx.TransportError`` 或 ``httpx.HTTPStatusError``。
    """
    max_retries = max(0, settings.max_retries)
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        await report(f"请求视觉后端（第 {attempt + 1} 次）：{url}")
        try:
            response = await client.post(
                url, json=json, headers=headers, params=params
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            # 429 / 5xx 可重试；其余 4xx 是请求本身的问题，重试也不会变好
            status = exc.response.status_code
            if status != 429 and status < 500:
                raise
            last_exc = exc
            delay = max(_backoff(attempt), _retry_after_seconds(exc))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            delay = _backoff(attempt)

        if attempt >= max_retries:
            break
        if not has_budget_for(delay):
            logger.debug("视觉后端剩余时间预算不足，停止第 {} 次重试", attempt + 1)
            break
        logger.debug(
            "视觉后端第 {} 次请求失败，{:.2f}s 后重试：{!r}",
            attempt + 1,
            delay,
            last_exc,
        )
        if delay > 0:
            await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("post_with_retry: 未执行任何请求")  # pragma: no cover
