"""视觉后端共用的 ``httpx.AsyncClient``。

五个适配器原先各自维护一份 client 单例（同一份 8 行代码 ×5），且从不关闭。
这里收敛为一个：MCP 服务常驻，一条连接池可被所有后端复用（各后端的
Host 不同，httpx 会按 origin 分池，共享 client 不影响正确性）。

与图片下载用的 client 不同：视觉请求走 ``trust_env=True``（默认），
因为大陆访问 OpenAI / Anthropic 常需 `HTTP_PROXY`，代理在这里是功能。
"""

from __future__ import annotations

import httpx

from openeye_mcp.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """返回复用的 ``AsyncClient``；首次调用时按当前超时配置创建。"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


async def aclose_client() -> None:
    """释放连接池（进程退出前调用）。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
