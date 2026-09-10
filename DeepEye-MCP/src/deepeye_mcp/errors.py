"""DeepEye 错误分类。

把底层异常映射为「分类 + 用户友好的中文提示」，供所有工具统一使用。

安全约定
--------
分类结果会进入 MCP 工具输出（agent context）与日志，因此**任何文案在
返回前都必须经过** :func:`redact_secrets` 脱敏。历史上 Gemini 后端把
API Key 放在 URL query（``?key=...``），``httpx.HTTPStatusError`` 的
文本包含完整 URL，经本模块拼接后会回显到工具输出——该路径现已封堵。
"""

from __future__ import annotations

import re

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


class ImageSourceError(ValueError):
    """图像来源解析失败。

    覆盖：本地文件缺失、URL 缺少主机名、主机无法解析、重定向异常、
    data URI 非法、SSRF 拦截、大小超限。

    继承 ``ValueError`` 以兼容既有捕获逻辑；作为独立类型可让
    :func:`classify_error` 不依赖中文关键词就归入 ``image`` 分类。
    """


# ─── 凭据脱敏 ────────────────────────────────────────────────────────────────
# 顺序敏感：先处理请求头式，再处理独立 Bearer，最后处理 URL query。

# x-api-key: VALUE / x-goog-api-key=VALUE / authorization: Bearer VALUE
_HEADER_SECRET_RE = re.compile(
    r"(?i)((?:x-api-key|x-goog-api-key|api-key|authorization)['\"]?\s*[:=]\s*)"
    r"(?:(?:bearer)\s+)?['\"]?([^\s,'\"}]+)"
)
# 独立 Bearer VALUE（如 RuntimeError 文案里直接拼了 token）
_BEARER_SECRET_RE = re.compile(r"(?i)\b(bearer)(\s+)([A-Za-z0-9._\-]{8,})")
# URL query / 报文片段：key=VALUE、api_key=VALUE、token=VALUE …
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(key|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|password|secret)"
    r"(=|%3D)([^&\s'\"]+)"
)

_REDACTED = "***"


def redact_secrets(text: str) -> str:
    """抹掉文本中的凭据片段，返回可安全外发的字符串。"""
    if not text:
        return text
    text = _HEADER_SECRET_RE.sub(rf"\g<1>{_REDACTED}", text)
    text = _BEARER_SECRET_RE.sub(rf"\g<1>\g<2>{_REDACTED}", text)
    text = _QUERY_SECRET_RE.sub(rf"\g<1>\g<2>{_REDACTED}", text)
    return text


def _backend_tag(provider: str) -> str:
    """后端错误文案前缀：配置了 provider 时带上它，便于定位是哪一路后端。"""
    return f"后端（{provider}）" if provider else "后端"


def classify_error(exc: Exception, provider: str = "") -> tuple[str, str]:
    """把异常分类为 ``(category, message)``。

    Args:
        exc: 捕获到的异常。
        provider: 当前视觉后端（openai/gemini/anthropic 等），会写入
            后端类错误文案，便于在多层后端配置下定位问题来源。

    Returns:
        ``(category, message)``；category 取值：
        config / network / timeout / backend / image / unknown。
        返回的 message 已脱敏，可安全外发。
    """
    msg = redact_secrets(str(exc))

    # 网络 / 超时（httpx 具体异常优先）
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", f"请求超时：{msg}。可增大 REQUEST_TIMEOUT 或换更快的端点。"
    if isinstance(exc, httpx.TransportError):
        return "network", f"网络错误：{msg}。请检查网络连接和 BASE_URL 配置。"

    # 后端 HTTP 错误
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        tag = _backend_tag(provider)
        if status == 400:
            return "backend", f"{tag}拒绝请求（400）：{msg}。可能原因：模型不支持某参数（如 reasoning_effort / response_format）。"
        if status in (401, 403):
            return "backend", f"{tag}认证失败（{status}）：{msg}。API Key 可能无效。"
        if status == 404:
            return "backend", f"{tag}资源不存在（404）：{msg}。请检查模型名或 BASE_URL。"
        if status == 429:
            return "backend", f"{tag}限流（429）：{msg}。已自动重试，仍失败请降低调用频率。"
        if status >= 500:
            return "backend", f"{tag}服务错误（{status}）：{msg}。已自动重试，仍失败请稍后再试。"
        return "backend", f"{tag}返回错误（{status}）：{msg}"

    # 图片类：来源解析失败（独立类型，不依赖中文关键词）
    if isinstance(exc, ImageSourceError):
        return "image", f"图片来源不可用：{msg}"
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
