"""Anthropic Claude 视觉适配器。

通过 Anthropic Messages API（``/v1/messages``）发送图文请求并返回文本描述。
与 OpenAI Chat Completions 协议差异较大：
- 认证用 ``x-api-key`` + ``anthropic-version`` 头（而非 Bearer）
- 图片用 ``image`` block（base64 无换行），置于该 turn 文本之前
- ``max_tokens`` 必填（无默认值）
- 响应 ``content`` 是 block 数组，需遍历拼接 ``type=="text"`` 的块
  （推理模型可能夹带 ``thinking`` 块，必须跳过）
- JSON 结构化输出走 ``output_config.format``（json_schema）
"""

from __future__ import annotations

import httpx

from deepeye_mcp.config import settings
from deepeye_mcp.vision._retry import post_with_retry
from deepeye_mcp.vision.base import VisionAdapter

# 复用单个 AsyncClient（与 openai_adapter 一致）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


def _extract_text(content: list | None) -> str:
    """从 Anthropic 响应 content 数组中提取文本。

    content 是 block 数组：``{"type": "text", "text": "..."}``、
    ``{"type": "thinking", "thinking": "..."}`` 等。
    只拼接 text 块（跳过 thinking/tool_use 等），并按 block 顺序保持原文。
    """
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


class AnthropicVisionAdapter(VisionAdapter):
    """基于 Anthropic Messages API 的视觉适配器。

    Args:
        model: 模型名称，未指定时使用 ``settings.anthropic_model``。
        api_key: API Key，未指定时使用 ``settings.anthropic_api_key``。
        base_url: 接口地址，未指定时使用 ``settings.anthropic_base_url``。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.anthropic_model
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        base = base_url if base_url is not None else settings.anthropic_base_url
        base = (base or "").strip()
        self.base_url = base if base else "https://api.anthropic.com/v1"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _build_payload(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None,
        reasoning_effort: str | None,
        response_format: dict | None,
    ) -> dict:
        """构造 Messages API payload。

        - 图片 block 置于该 turn 文本之前（官方推荐，效果最好）
        - JSON 输出：openai 式 ``{"type": "json_object"}`` 映射为
          ``output_config.format``（json_schema）；其余忽略
        - reasoning_effort：当前模型用 ``output_config.effort``（low/medium/high）
        """
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        # 结构化输出：json_object -> output_config.format (json_schema)
        if response_format and response_format.get("type") == "json_object":
            payload["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "name": "vision_result",
                    "strict": True,
                    "schema": {"type": "object"},
                }
            }
        # 推理深度：映射到 output_config.effort（旧模型不支持时忽略）
        effort = reasoning_effort or settings.reasoning_effort
        if effort:
            oc = payload.setdefault("output_config", {})
            oc["effort"] = effort
        return payload

    async def describe(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """调用 Anthropic Messages API 返回图像描述文本。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时由
                ``raise_for_status()`` 抛出。
        """
        url = f"{self.base_url.rstrip('/')}/messages"
        payload = self._build_payload(
            image_b64, mime_type, prompt, max_tokens,
            reasoning_effort, response_format,
        )
        headers = self._headers()

        client = _get_client()
        response = await post_with_retry(client, url, json=payload, headers=headers)

        data = response.json()
        return _extract_text(data.get("content"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：messages 只有 user 文本，无图片。"""
        url = f"{self.base_url.rstrip('/')}/messages"
        payload = {
            "model": self.model,
            "max_tokens": settings.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if settings.reasoning_effort:
            payload["output_config"] = {"effort": settings.reasoning_effort}
        headers = self._headers()

        client = _get_client()
        response = await post_with_retry(client, url, json=payload, headers=headers)
        data = response.json()
        return _extract_text(data.get("content"))