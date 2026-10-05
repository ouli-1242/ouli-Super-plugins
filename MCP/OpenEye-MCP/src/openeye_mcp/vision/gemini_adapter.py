"""Google Gemini 视觉适配器。

通过 Gemini ``generateContent`` API 发送图文请求并返回文本，
``inline_data`` 携带 base64 图像，``text`` 部分携带提示词。
"""

from __future__ import annotations

from openeye_mcp.vision._http import get_client as _get_client
from openeye_mcp.vision._retry import post_with_retry
from openeye_mcp.vision.base import VisionAdapter, VisionOptions

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _extract_text(data: dict) -> str:
    """从 ``candidates[0].content.parts[0].text`` 取文本，结构异常时返回空串。"""
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        text = None
    return (text or "").strip()


class GeminiVisionAdapter(VisionAdapter):
    """基于 Google Gemini ``generateContent`` 的视觉适配器。

    Args:
        model: 模型名称，未指定时使用 ``settings.gemini_model``。
        api_key: API Key，未指定时使用 ``settings.gemini_api_key``。
        base_url: 接口地址，未指定时回退到官方
            ``https://generativelanguage.googleapis.com/v1beta``。
    """

    settings_prefix = "gemini"
    default_base_url = _DEFAULT_BASE_URL

    @property
    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"

    def _generation_config(self, options: VisionOptions) -> dict:
        """``generationConfig``：token 上限与 JSON 输出声明。

        历史缺陷：仅当调用方显式传了 ``max_tokens`` 才写 maxOutputTokens，
        既不回落 ``settings.max_tokens``，也让配置层对该后端实际不生效。
        """
        config: dict = {"maxOutputTokens": options.max_tokens}
        # Gemini 没有 OpenAI 式 response_format，不映射则 JSON 稳定性承诺
        # 在 Gemini 上静默失效
        if options.wants_json:
            config["responseMimeType"] = "application/json"
        return config

    async def describe(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """调用 Gemini ``generateContent`` 返回图像理解文本。

        Args:
            reasoning_effort: 忽略（Gemini 无此参数）。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时抛出。
        """
        options = VisionOptions.resolve(max_tokens, reasoning_effort, response_format)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": self._generation_config(options),
        }
        response = await post_with_retry(
            _get_client(),
            self._url,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
        )
        return _extract_text(response.json())

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：generateContent parts 仅含 text，无 inline_data。"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": self._generation_config(VisionOptions.resolve()),
        }
        response = await post_with_retry(
            _get_client(),
            self._url,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
        )
        return _extract_text(response.json())
