"""Google Gemini 视觉适配器。

通过 Gemini ``generateContent`` API 发送图文请求并返回文本描述，
``inline_data`` 携带 base64 图像，``text`` 部分携带提示词。
"""

from __future__ import annotations

import httpx

from deepeye_mcp.config import settings
from deepeye_mcp.vision.base import VisionAdapter

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# 复用单个 AsyncClient，避免每次请求新建连接（与 openai_adapter 一致）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


class GeminiVisionAdapter(VisionAdapter):
    """基于 Google Gemini ``generateContent`` 的视觉适配器。

    Args:
        model: 模型名称，未指定时使用 ``settings.gemini_model``。
        api_key: API Key，未指定时使用 ``settings.gemini_api_key``。
        base_url: 接口地址，未指定时回退到官方
            ``https://generativelanguage.googleapis.com/v1beta``。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.gemini_model
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.base_url = (
            base_url.strip()
            if base_url and base_url.strip()
            else _DEFAULT_BASE_URL
        )

    async def describe(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """调用 Gemini ``generateContent`` 返回图像描述文本。

        Args:
            max_tokens: 输出 token 上限覆盖；None 时使用 ``settings.max_tokens``。
            reasoning_effort: 忽略（Gemini 无此参数）。
            response_format: 忽略（Gemini 无此参数）。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时由
                ``raise_for_status()`` 抛出。
        """
        url = f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                        {"text": prompt},
                    ]
                }
            ]
        }
        if max_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": max_tokens}
        # 映射 response_format json_object -> Gemini generationConfig.responseMimeType。
        # Gemini 没有 OpenAI 式 response_format，若不映射会被静默忽略，
        # 导致 JSON 稳定性承诺在 Gemini 上失效且无感知。
        if response_format and response_format.get("type") == "json_object":
            gen = payload.setdefault("generationConfig", {})
            gen["responseMimeType"] = "application/json"
        headers = {"Content-Type": "application/json"}

        timeout = settings.request_timeout
        last_exc: Exception | None = None
        client = _get_client()
        for attempt in range(settings.max_retries + 1):
            try:
                response = await client.post(url, params=params, json=payload, headers=headers)
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
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            text = None
        return (text or "").strip()

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：generateContent parts 仅含 text，无 inline_data。"""
        url = f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        headers = {"Content-Type": "application/json"}
        client = _get_client()
        response = await client.post(url, params=params, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            text = None
        return (text or "").strip()
