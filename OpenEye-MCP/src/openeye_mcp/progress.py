"""向 MCP 客户端上报工具调用进度。

客户端普遍按「多久没收到任何消息」判定一次 stdio 调用死掉，而一次布局 /
表格分析可能连打好几次视觉后端、每次再乘上重试。带上 ``progressToken``
时，重试逻辑每发起一次请求就上报一个递增计数，客户端据此知道「还在干活」，
不必在结果真的能出来之前把调用掐掉（白烧一次配额）。

实现用 contextvar 传递上报函数：工具与适配器都不必为进度而多一层参数，
没有 token 时 ``report`` 是纯 no-op。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import ContextVar

Reporter = Callable[[str], Coroutine[None, None, None]] | None

_reporter: ContextVar[Reporter] = ContextVar("openeye_progress_reporter", default=None)


@asynccontextmanager
async def progress_scope(reporter: Reporter) -> AsyncIterator[None]:
    """在当前任务内安装进度上报函数。"""
    token = _reporter.set(reporter)
    try:
        yield
    finally:
        _reporter.reset(token)


async def report(message: str) -> None:
    """上报一次进度；未安装上报函数时什么都不做。"""
    reporter = _reporter.get()
    if reporter is not None:
        await reporter(message)
