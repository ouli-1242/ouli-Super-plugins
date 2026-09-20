"""视觉适配器包。

对外暴露 :func:`create_vision_adapter`（实现在 :mod:`.registry`）与
抽象基类 :class:`VisionAdapter` / :class:`VisionOptions`。
"""

from __future__ import annotations

from openeye_mcp.vision.anthropic_adapter import AnthropicVisionAdapter
from openeye_mcp.vision.base import VisionAdapter, VisionOptions
from openeye_mcp.vision.gemini_adapter import GeminiVisionAdapter
from openeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
from openeye_mcp.vision.openai_adapter import OpenAIVisionAdapter
from openeye_mcp.vision.registry import (
    ADAPTERS,
    SUPPORTED_PROVIDERS,
    create_vision_adapter,
    normalize_provider,
)
from openeye_mcp.vision.responses_adapter import ResponsesVisionAdapter

__all__ = [
    "VisionAdapter",
    "VisionOptions",
    "OpenAIVisionAdapter",
    "GeminiVisionAdapter",
    "AnthropicVisionAdapter",
    "ResponsesVisionAdapter",
    "GeminiInteractionsAdapter",
    "ADAPTERS",
    "SUPPORTED_PROVIDERS",
    "create_vision_adapter",
    "normalize_provider",
]
