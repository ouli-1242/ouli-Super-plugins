"""OpenAI Responses API 视觉适配器。

通过 OpenAI 官方 Responses 协议（``/v1/responses``）发送图文请求。
与 Chat Completions 的差异：
- 请求体用 ``input`` 数组（非 ``messages``）+ 顶层 ``instructions``
- 图片用 ``input_image`` block（``{"type": "input_image", "image_url": "data:..."}``）
- 响应 ``output`` 是类型化 Item 数组，需遍历找 ``type=="message"`` 的文本
- 结构化输出走 ``text.format``（json_schema）
- token 上限是 ``max_output_tokens``，推理深度是顶层 ``reasoning.effort``

第三方 OpenAI 兼容厂商大多实现 Chat Completions 而非 Responses，
本适配器主要面向 OpenAI / Azure 官方端点。
"""

from __future__ import annotations

from openeye_mcp.vision._http import get_client as _get_client
from openeye_mcp.vision._retry import post_with_retry
from openeye_mcp.vision.base import VisionAdapter, VisionOptions

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


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

    settings_prefix = "responses"
    default_base_url = _DEFAULT_BASE_URL

    @property
    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/responses"

    def _build_payload(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        options: VisionOptions,
        *,
        with_image: bool = True,
    ) -> dict:
        """构造 Responses API payload。

        - input 数组：``{"type": "input_image", "image_url": "data:..."}`` + 文本
        - 结构化输出：``text.format``（json_schema）
        - reasoning_effort：顶层 ``reasoning`` 的 ``effort``
        """
        text_block: dict = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }
        blocks: list[dict] = []
        if with_image:
            blocks.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{image_b64}",
                }
            )
        blocks.append(text_block)
        payload: dict = {
            "model": self.model,
            "input": blocks,
            "max_output_tokens": options.max_tokens,
        }
        if options.wants_json:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "vision_result",
                    "strict": True,
                    "schema": {"type": "object"},
                }
            }
        if options.reasoning_effort:
            payload["reasoning"] = {"effort": options.reasoning_effort}
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
        """调用 OpenAI Responses API 返回图像理解文本。

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
            _get_client(), self._url, json=payload, headers=self.bearer_headers()
        )
        return _extract_output_text(response.json().get("output"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：input 只有文本，无图片。"""
        payload = self._build_payload(
            "", "", prompt, VisionOptions.resolve(), with_image=False
        )
        response = await post_with_retry(
            _get_client(), self._url, json=payload, headers=self.bearer_headers()
        )
        return _extract_output_text(response.json().get("output"))
