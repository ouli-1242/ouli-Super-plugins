"""Google Gemini Interactions API 视觉适配器。

通过 Gemini 新版 ``Interactions API``（``POST /v1beta/interactions``）发送
图文请求。与 ``generateContent`` 的差异：
- 请求体用顶层 ``model`` + ``input`` 数组（图片 ``{type:"image", data, mime_type}``）
- 响应是 ``steps[]`` 时间线，取 ``type=="model_output"`` 的文本
  （Gemini 3.x 默认 thinking，需跳过非 model_output 块）
- JSON 结构化输出走顶层 ``response_format``
- 默认 ``store=true``（服务端留存 55 天）；临时图片显式 ``store=false``
"""

from __future__ import annotations

import httpx

from deepeye_mcp.config import settings
from deepeye_mcp.vision.base import VisionAdapter

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# 复用单个 AsyncClient
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.request_timeout)
    return _client


def _extract_steps_text(steps: list | None) -> str:
    """从 Interactions 响应 steps 时间线中提取文本。

    steps 元素：``{"type": "model_output", "content": [{"type": "text", "text": "..."}]}``、
    ``{"type": "user_input", ...}``、``{"type": "function_call", ...}`` 等。
    只取 model_output 里 text 内容，跳过 thinking 等。
    """
    if not steps:
        return ""
    parts: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        parts.append(text)
        elif isinstance(content, dict) and content.get("type") == "text":
            text = content.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


class GeminiInteractionsAdapter(VisionAdapter):
    """基于 Gemini Interactions API 的视觉适配器。

    复用 ``GEMINI_API_KEY`` / ``GEMINI_MODEL`` / ``GEMINI_BASE_URL`` 配置
    （与 generateContent 同一 Google 账号），仅协议不同。
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

    def _build_payload(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None,
        response_format: dict | None,
    ) -> dict:
        """构造 Interactions API payload。

        - input 数组：图片 block + 文本 message
        - ``store=false``：临时图片不留存在 Google 服务端
        - JSON 输出：``response_format`` 数组（application/json）
        """
        input_items: list[dict] = [
            {"type": "image", "data": image_b64, "mime_type": mime_type},
            {"type": "text", "text": prompt},
        ]
        payload: dict = {
            "model": self.model,
            "input": input_items,
            "store": False,
        }
        if response_format and response_format.get("type") == "json_object":
            payload["response_format"] = [
                {"type": "text", "mime_type": "application/json", "schema": {"type": "object"}}
            ]
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
        """调用 Gemini Interactions API 返回图像描述文本。

        Args:
            max_tokens: 输出 token 上限覆盖；None 时使用 ``settings.max_tokens``。
            reasoning_effort: 忽略（Interactions 无此参数）。
            response_format: 输出格式约束（如 ``{"type": "json_object"}``）。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时抛出。
        """
        url = f"{self.base_url.rstrip('/')}/interactions"
        params = {"key": self.api_key}
        payload = self._build_payload(
            image_b64, mime_type, prompt, max_tokens, response_format
        )
        headers = {"Content-Type": "application/json"}

        client = _get_client()
        last_exc: Exception | None = None
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
        return _extract_steps_text(data.get("steps"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：input 只有文本，无图片。"""
        url = f"{self.base_url.rstrip('/')}/interactions"
        params = {"key": self.api_key}
        payload = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt}],
            "store": False,
        }
        headers = {"Content-Type": "application/json"}

        client = _get_client()
        response = await client.post(url, params=params, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return _extract_steps_text(data.get("steps"))