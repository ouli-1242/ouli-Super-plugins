"""视觉适配器包。

提供抽象基类 :class:`VisionAdapter` 与工厂函数
:func:`create_vision_adapter`，根据配置创建具体适配器实例。
"""

from __future__ import annotations

from deepeye_mcp.config import settings
from deepeye_mcp.vision.anthropic_adapter import AnthropicVisionAdapter
from deepeye_mcp.vision.base import VisionAdapter
from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter
from deepeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
from deepeye_mcp.vision.openai_adapter import OpenAIVisionAdapter
from deepeye_mcp.vision.responses_adapter import ResponsesVisionAdapter

__all__ = [
    "VisionAdapter",
    "OpenAIVisionAdapter",
    "GeminiVisionAdapter",
    "AnthropicVisionAdapter",
    "ResponsesVisionAdapter",
    "GeminiInteractionsAdapter",
    "create_vision_adapter",
]


def create_vision_adapter(
    model_override: str | None = None,
    provider: str | None = None,
) -> VisionAdapter:
    """根据 ``settings.vision_provider`` 创建对应视觉适配器实例。

    Args:
        model_override: 可选的模型名称覆盖；未指定时使用配置默认值。
        provider: 可选的视觉后端覆盖（openai / gemini / anthropic /
            responses）；未指定时使用 ``settings.vision_provider``。用于
            ``extract_text`` 按 ``settings.ocr_backend`` 指定 OCR 后端。

    Returns:
        :class:`VisionAdapter` 具体实例。

    Raises:
        ValueError: 不支持的 provider。
    """
    provider = (provider or settings.vision_provider).lower().strip()
    if provider == "openai":
        return OpenAIVisionAdapter(model=model_override)
    if provider == "gemini":
        return GeminiVisionAdapter(model=model_override)
    if provider == "anthropic":
        return AnthropicVisionAdapter(model=model_override)
    if provider == "responses":
        return ResponsesVisionAdapter(model=model_override)
    if provider == "gemini-interactions":
        return GeminiInteractionsAdapter(model=model_override)
    raise ValueError(f"不支持的视觉后端: {provider!r}")
