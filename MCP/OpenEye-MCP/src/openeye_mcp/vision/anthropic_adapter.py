"""Anthropic Claude 视觉适配器。

通过 Anthropic Messages API（``/v1/messages``）发送图文请求并返回文本。
与 OpenAI Chat Completions 协议差异较大：
- 认证用 ``x-api-key`` + ``anthropic-version`` 头（而非 Bearer）
- 图片用 ``image`` block（base64 无换行），置于该 turn 文本之前
- ``max_tokens`` 必填（无默认值）
- 响应 ``content`` 是 block 数组，需遍历拼接 ``type=="text"`` 的块
  （推理模型可能夹带 ``thinking`` 块，必须跳过）
- JSON 结构化输出走 ``output_config.format``（json_schema）
"""

from __future__ import annotations

from openeye_mcp.vision._http import get_client as _get_client
from openeye_mcp.vision._retry import post_with_retry
from openeye_mcp.vision.base import VisionAdapter, VisionOptions

_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


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

    settings_prefix = "anthropic"
    default_base_url = _DEFAULT_BASE_URL

    @property
    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/messages"

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
        options: VisionOptions,
    ) -> dict:
        """构造 Messages API payload。

        - 图片 block 置于该 turn 文本之前（官方推荐，效果最好）
        - JSON 输出：openai 式 ``{"type": "json_object"}`` 映射为
          ``output_config.format``（json_schema）
        - 推理深度：映射到 ``output_config.effort``（旧模型不支持时忽略）
        """
        payload: dict = {
            "model": self.model,
            "max_tokens": options.max_tokens,
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
        if options.wants_json:
            payload["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "name": "vision_result",
                    "strict": True,
                    "schema": {"type": "object"},
                }
            }
        if options.reasoning_effort:
            payload.setdefault("output_config", {})["effort"] = options.reasoning_effort
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
        """调用 Anthropic Messages API 返回图像理解文本。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码时抛出。
        """
        payload = self._build_payload(
            image_b64,
            mime_type,
            prompt,
            VisionOptions.resolve(max_tokens, reasoning_effort, response_format),
        )
        response = await post_with_retry(
            _get_client(), self._url, json=payload, headers=self._headers()
        )
        return _extract_text(response.json().get("content"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：messages 只有 user 文本，无图片。"""
        options = VisionOptions.resolve()
        payload: dict = {
            "model": self.model,
            "max_tokens": options.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if options.reasoning_effort:
            payload["output_config"] = {"effort": options.reasoning_effort}
        response = await post_with_retry(
            _get_client(), self._url, json=payload, headers=self._headers()
        )
        return _extract_text(response.json().get("content"))
