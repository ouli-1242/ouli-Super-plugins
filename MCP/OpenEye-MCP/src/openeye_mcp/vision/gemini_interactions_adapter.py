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

from openeye_mcp.vision._http import get_client as _get_client
from openeye_mcp.vision._retry import post_with_retry
from openeye_mcp.vision.base import VisionAdapter, VisionOptions

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _extract_steps_text(steps: list | None) -> str:
    """从 Interactions 响应 steps 时间线中提取文本。

    steps 元素：``{"type": "model_output", "content": [...]}``、
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

    settings_prefix = "gemini"
    default_base_url = _DEFAULT_BASE_URL

    @property
    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/interactions"

    def _build_payload(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        options: VisionOptions,
        *,
        with_image: bool = True,
    ) -> dict:
        """构造 Interactions API payload。

        - input 数组：图片 block + 文本 message
        - ``store=false``：临时图片不留存在 Google 服务端
        - JSON 输出：``response_format`` 数组（application/json）
        - token 上限：``max_output_tokens``。历史缺陷是收下调用方传的
          ``max_tokens`` 却从不写进 payload，布局/表格的 8192 被静默丢弃、
          配置默认值也一并失效；字段名按本协议与 Responses 同族
          （``model`` / ``input`` / ``store`` 均为顶层字段）推断。
        """
        input_items: list[dict] = []
        if with_image:
            input_items.append(
                {"type": "image", "data": image_b64, "mime_type": mime_type}
            )
        input_items.append({"type": "text", "text": prompt})
        payload: dict = {
            "model": self.model,
            "input": input_items,
            "store": False,
            "max_output_tokens": options.max_tokens,
        }
        if options.wants_json:
            payload["response_format"] = [
                {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": {"type": "object"},
                }
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
        """调用 Gemini Interactions API 返回图像理解文本。

        Args:
            max_tokens: 输出 token 上限覆盖；None 时用 ``settings.max_tokens``。
            reasoning_effort: 忽略（Interactions 无此参数）。
            response_format: 输出格式约束（如 ``{"type": "json_object"}``）。

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
            _get_client(),
            self._url,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
        )
        return _extract_steps_text(response.json().get("steps"))

    async def describe_text(self, prompt: str) -> str:
        """纯文本请求：input 只有文本，无图片。"""
        payload = self._build_payload(
            "", "", prompt, VisionOptions.resolve(), with_image=False
        )
        response = await post_with_retry(
            _get_client(),
            self._url,
            json=payload,
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
        )
        return _extract_steps_text(response.json().get("steps"))
