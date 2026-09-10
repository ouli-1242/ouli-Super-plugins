"""DeepEye 错误分类。

把底层异常映射为「分类 + 用户友好的中文提示」，供所有工具统一使用。
"""

from __future__ import annotations

import httpx


class VisionError(Exception):
    """工具级失败异常：携带面向用户的错误文案。

    tools.py 各工具失败分支捕获底层异常后抛出本异常（文案与旧版一致），
    server.py 的 ``call_tool`` 最外层捕获它并返回 ``isError=True`` 的
    ``CallToolResult``，让调用方（agent）能区分正常结果与失败。
    """

    def __init__(self, message: str, category: str = "unknown") -> None:
        super().__init__(message)
        self.category = category


def classify_error(exc: Exception, provider: str = "") -> tuple[str, str]:
    """把异常分类为 ``(category, message)``。

    Args:
        exc: 捕获到的异常。
        provider: 当前视觉后端（openai/gemini/anthropic 等），预留用于针对性提示。

    Returns:
        ``(category, message)``；category 取值：
        config / network / timeout / backend / image / unknown。
    """
    msg = str(exc)

    # 网络 / 超时（httpx 具体异常优先）
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", f"请求超时：{msg}。可增大 REQUEST_TIMEOUT 或换更快的端点。"
    if isinstance(exc, httpx.TransportError):
        return "network", f"网络错误：{msg}。请检查网络连接和 BASE_URL 配置。"

    # 后端 HTTP 错误
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 400:
            return "backend", f"后端拒绝请求（400）：{msg}。可能原因：模型不支持某参数（如 reasoning_effort / response_format）。"
        if status in (401, 403):
            return "backend", f"后端认证失败（{status}）：{msg}。API Key 可能无效。"
        if status == 404:
            return "backend", f"后端资源不存在（404）：{msg}。请检查模型名或 BASE_URL。"
        if status == 429:
            return "backend", f"后端限流（429）：{msg}。请稍后重试或降低调用频率。"
        if status >= 500:
            return "backend", f"后端服务错误（{status}）：{msg}。请稍后重试。"
        return "backend", f"后端返回错误（{status}）：{msg}"

    # 图片类
    if isinstance(exc, FileNotFoundError):
        return "image", f"图片文件不存在：{msg}"
    if isinstance(exc, ValueError):
        if "SSRF" in msg:
            return "image", f"图片来源被安全策略拦截：{msg}"
        if "大小上限" in msg:
            return "image", f"图片超过大小上限：{msg}"
        if any(kw in msg for kw in ("未设置", "未配置", "不支持的", "缺少")):
            return "config", f"配置错误：{msg} 请在 MCP 配置的 env 或 .env 中设置。"
    if isinstance(exc, KeyError):
        return "config", f"配置错误：缺少必填参数 {msg}"

    # OpenAI 适配器把 timeout/transport 包装成 RuntimeError
    if isinstance(exc, RuntimeError):
        if "超时" in msg:
            return "timeout", msg
        if "网络" in msg:
            return "network", msg

    # 未知
    return "unknown", msg