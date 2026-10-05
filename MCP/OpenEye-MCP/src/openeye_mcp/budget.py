"""单次工具调用的时间预算。

最坏情况下的请求数是相乘的：布局/表格外层重试 × 主请求与降级请求 ×
``post_with_retry`` 的内层重试 × 单次超时，可以轻易累计到几十分钟，
而 MCP 客户端早已按自己的超时把这次调用判死——钱烧了，结果没人要。

这里用 contextvar 存一个 monotonic 截止时刻：``server.call_tool`` 进入
工具前设定，重试逻辑（:mod:`openeye_mcp.vision._retry` 与 tools 的外层
循环）在**睡眠或再发一次请求前** consult 它，剩余不足就放弃重试并把已经
拿到的结果返回。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_deadline: ContextVar[float | None] = ContextVar("openeye_deadline", default=None)


def remaining_seconds() -> float | None:
    """预算剩余秒数；未设定预算时返回 ``None``。"""
    deadline = _deadline.get()
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def has_budget_for(seconds: float) -> bool:
    """判断剩余预算是否够再等 ``seconds``；无预算限制时恒为 True。"""
    remaining = remaining_seconds()
    return remaining is None or remaining > seconds


@contextmanager
def budget(seconds: float) -> Iterator[None]:
    """为当前调用设定总时间预算（``seconds <= 0`` 表示不设限）。"""
    token: Token = _deadline.set(
        time.monotonic() + seconds if seconds and seconds > 0 else None
    )
    try:
        yield
    finally:
        _deadline.reset(token)
