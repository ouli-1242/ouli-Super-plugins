"""视觉后端共用的 HTTP POST 重试。

五个适配器原先各自复制了一份重试循环，并且只捕获
``TimeoutException`` / ``TransportError``——服务端 429 限流与 5xx 故障
不重试，与错误文案「请稍后重试」自相矛盾（历史缺陷）。这里收敛为一份：

- **重试**：``TimeoutException`` / ``TransportError`` / 429 / 5xx
- **不重试**：其余 4xx（400 / 401 / 403 / 404…）——重试无意义且白耗配额
- **退避**：``retry_backoff * 2**(n-1)``，``retry_backoff=0`` 可关闭（测试用）
- **耗尽**：抛出最后一次异常并保留原始类型，交由
  :func:`deepeye_mcp.errors.classify_error` 统一分类
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from deepeye_mcp.config import settings

logger = logging.getLogger(__name__)


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
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc

        if attempt < max_retries:
            delay = settings.retry_backoff * (2 ** attempt)
            logger.debug(
                "视觉后端第 %d 次请求失败，%.2fs 后重试：%r",
                attempt + 1,
                delay,
                last_exc,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("post_with_retry: 未执行任何请求")  # pragma: no cover
