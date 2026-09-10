"""OpenAI Responses API 视觉适配器。

通过 OpenAI 官方 Responses 协议（``/v1/responses``）发送图文请求。
与 Chat Completions 的差异：
- 请求体用 ``input`` 数组（非 ``messages``）+ 顶层 ``instructions``
- 图片用 ``input_image`` block（``{"type": "input_image", "image_url": "data:..."}``）
- 响应 ``output`` 是类型化 Item 数组，需遍历找 ``type=="message"`` 的文本
- 结构化输出走 ``text.format``（json_schema）

第三方 OpenAI 兼容厂商大多实现 Chat Completions 而非 Responses，
本适配器主要面向 OpenAI / Azure 官方端点。
"""

from __future__ import annotations

import httpx

from deepeye_mcp.config import settings
from deepeye_mcp.vision.base import VisionAdapter

# 复用单个 AsyncClient
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


def _extract_output_text(output: list | None) -> str:
    """从 Responses API 响应 output 数组中提取文本。

    output 是类型化 Item 数组：``{"type": "message", "content": [...]}``、
    ``{"type": "reasoning", ...}``、``{"type": "function_call", ...}`` 等。
    只取 ``type=="message"`` 的 content 里 ``type=="output_text"`` 的 text。
    """
    if not output:
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


class ResponsesVisionAdapter(VisionAdapter):
    """基于 OpenAI Responses API 的视觉适配器。

    Args:
        model: 模型名称，未指定时使用 ``settings.responses_model``。
        api_key: API Key，未指定时使用 ``settings.responses_api_key``。
        base_url: 接口地址，未指定时使用 ``settings.responses_base_url``。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.responses_model
        self.api_key = api_key if api_key is not None else settings.responses_api_key
        base = base_url if base_url is not None else settings.responses_base_url
        base = (base or "").strip()
        self.base_url = base if base else "https://api.openai.com/v1"

    def _build_payload(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None,
        reasoning_effort: str | None,
        response_format: dict | None,
    ) -> dict:
        """构造 Responses API payload。

        - input 数组：``{"type": "input_image", "image_url": "data:..."}`` + 文本
        - 结构化输出：``text.format``（json_schema）
        - reasoning_effort：顶层 ``reasoning`` 的 ``effort``
        """
        data_uri = f"data:{mime_type};base64,{image_b64}"
        payload: dict = {
            "model": self.model,
            "input": [
                {"type": "input_image", "image_url": data_uri},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]},
            ],
            "max_output_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
        }
        # 结构化输出：openai 式 json_object -> text.format (json_schema)
        if response_format and response_format.get("type") == "json_object":
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "vision_result",
                    "strict": True,
                    "schema": {"type": "object"},
                }
            }
        # 推理深度：reasoning.effort（low/medium/high）
        effort = reasoning_effort or settings.reasoning_effort
        if effort:
            payload["reasoning"] = {"effort": effort}
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
        """调用 OpenAI Responses API 返回图像描述文本。"""
        url = f"{self.base_url.rstrip('/')}/responses"
        payload = self._build_payload(
            image_b64, mime_type, prompt, max_tokens,
            reasoning_effort, response_format,
        )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = _get_client()
        last_exc: Exception | None = None
        for attempt in range(settings.max_retries + 1):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < settings.max_retries:
                    continue
                raise
        else:
            if last_exc:
                raise last_exc

        data = response.json()
        return _extract_output_text(data.get("output"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：input 只有文本，无图片。"""
        url = f"{self.base_url.rstrip('/')}/responses"
        payload: dict = {
            "model": self.model,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "max_output_tokens": settings.max_tokens,
        }
        if settings.reasoning_effort:
            payload["reasoning"] = {"effort": settings.reasoning_effort}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = _get_client()
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return _extract_output_text(data.get("output"))