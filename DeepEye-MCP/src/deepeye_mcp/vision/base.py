"""视觉适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class VisionAdapter(ABC):
    """视觉理解适配器抽象基类。

    具体实现通过 OpenAI / Gemini / 自定义兼容服务等后端完成图像理解，
    上层工具函数仅依赖此接口，实现后端可插拔。
    """

    @abstractmethod
    async def describe(
        self,
        image_b64: str,
        mime_type: str,
        prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """根据 ``prompt`` 对给定图像进行视觉理解并返回文本结果。

        Args:
            image_b64: 图像的 base64 编码字符串（不含 data URI 前缀）。
            mime_type: 图像 MIME 类型，例如 ``image/png``。
            prompt: 描述 / 提问 / OCR 等场景的提示词。
            max_tokens: 输出 token 上限覆盖；None 时使用配置默认值。
            reasoning_effort: 推理深度覆盖（如 low/medium/high）；None 时用配置默认。
            response_format: 输出格式约束（如 ``{"type": "json_object"}``）。

        Returns:
            视觉模型返回的文本结果。
        """
        ...

    @abstractmethod
    async def describe_text(self, prompt: str) -> str:
        """纯文本请求（无图片），用于跨图汇总等场景。

        Args:
            prompt: 提示词。

        Returns:
            模型返回的文本。
        """
        ...
