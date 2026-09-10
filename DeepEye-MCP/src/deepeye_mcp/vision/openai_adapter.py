"""OpenAI 兼容视觉适配器。

通过 OpenAI Chat Completions API（兼容任何 OpenAI 格式服务，例如 Azure
OpenAI、代理、第三方兼容服务）发送图文请求并返回文本描述。
"""

from __future__ import annotations

import httpx

from deepeye_mcp.config import settings
from deepeye_mcp.vision._retry import post_with_retry
from deepeye_mcp.vision.base import VisionAdapter

_DEFAULT_BASE_URL = "https://api.openai.com/v1"

# 推理模型（如 step_plan 端点）偶发 content 为空：重试次数
_EMPTY_CONTENT_RETRIES = 1

# 复用单个 AsyncClient，避免每次请求新建连接；MCP 服务常驻，连接可复用
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


def _extract_message(data: dict) -> dict | None:
    """从 Chat Completions 响应中稳健提取首个 message。

    部分后端偶发返回病态响应（``choices`` 缺失 / 为 None / 空数组），
    结构异常时返回 None，由调用方按「空内容」降级处理。
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    return message if isinstance(message, dict) else None


class OpenAIVisionAdapter(VisionAdapter):
    """基于 OpenAI Chat Completions 的视觉适配器。

    Args:
        model: 模型名称，未指定时使用 ``settings.openai_model``。
        api_key: API Key，未指定时使用 ``settings.openai_api_key``。
        base_url: 接口地址，未指定时使用 ``settings.openai_base_url``，
            仍为空则回退到官方 ``https://api.openai.com/v1``。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.openai_model
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        base = base_url if base_url is not None else settings.openai_base_url
        self.base_url = base.strip() if base and base.strip() else _DEFAULT_BASE_URL

    async def describe(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """调用 OpenAI Chat Completions 返回图像描述文本。

        Args:
            max_tokens: 输出 token 上限覆盖；None 时使用 ``settings.max_tokens``。
            reasoning_effort: 推理深度覆盖；None 时用 ``settings.reasoning_effort``。
            response_format: 输出格式约束（如 ``{"type": "json_object"}``）。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时由
                ``raise_for_status()`` 抛出。
        """
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        data_uri = f"data:{mime_type};base64,{image_b64}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
        }
        # reasoning_effort 仅在显式配置时发送：部分后端不支持该参数
        effort = reasoning_effort or settings.reasoning_effort
        if effort:
            payload["reasoning_effort"] = effort
        if response_format:
            payload["response_format"] = response_format
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = _get_client()
        timeout = settings.request_timeout
        # 重试交给共享助手；这里只把「已耗尽」的失败翻译成带建议的中文文案
        try:
            response = await post_with_retry(client, url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"视觉模型请求超时（{timeout}s），已重试 {settings.max_retries} 次。"
                f"建议：1) 缩短 prompt；2) 增大 REQUEST_TIMEOUT；3) 换更快的 API 端点。"
            ) from exc
        except httpx.TransportError as exc:
            raise RuntimeError(
                f"网络传输错误：{exc}。建议检查网络或 OPENAI_BASE_URL 配置。"
            ) from exc

        data = response.json()
        message = _extract_message(data)
        content = (message.get("content") or "").strip() if message else ""
        if content:
            return content

        # content 为空：推理模型偶发把答案放到 reasoning_content，先重试拿到干净答案
        for _ in range(_EMPTY_CONTENT_RETRIES):
            try:
                response = await post_with_retry(client, url, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError):
                break
            data = response.json()
            message = _extract_message(data)
            content = (message.get("content") or "").strip() if message else ""
            if content:
                return content

        # 重试仍空，回退到 reasoning_content（含完整答案，但可能带思考过程）
        return (message.get("reasoning_content") or "").strip() if message else ""

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：messages 只有 user 文本，无图片。"""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": settings.max_tokens,
        }
        if settings.reasoning_effort:
            payload["reasoning_effort"] = settings.reasoning_effort
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = _get_client()
        response = await post_with_retry(client, url, json=payload, headers=headers)
        data = response.json()
        message = _extract_message(data)
        content = (message.get("content") or "").strip() if message else ""
        if not content:
            content = (message.get("reasoning_content") or "").strip() if message else ""
        return content
