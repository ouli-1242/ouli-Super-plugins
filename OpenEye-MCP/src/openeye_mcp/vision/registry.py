"""provider → 适配器类的唯一映射。

新增后端只需在这里登记一行 + 写好适配器：`VisionProvider`（配置层校验）、
`create_vision_adapter`（运行时分发）与文档的可选值都从这里取，原先
「config 两份字面量 + 工厂 if 级联 + import + __all__」的分散改动收敛为一处。
"""

from __future__ import annotations

from openeye_mcp.config import settings
from openeye_mcp.vision.anthropic_adapter import AnthropicVisionAdapter
from openeye_mcp.vision.base import VisionAdapter
from openeye_mcp.vision.gemini_adapter import GeminiVisionAdapter
from openeye_mcp.vision.gemini_interactions_adapter import GeminiInteractionsAdapter
from openeye_mcp.vision.openai_adapter import OpenAIVisionAdapter
from openeye_mcp.vision.responses_adapter import ResponsesVisionAdapter

ADAPTERS: dict[str, type[VisionAdapter]] = {
    "openai": OpenAIVisionAdapter,
    "gemini": GeminiVisionAdapter,
    "anthropic": AnthropicVisionAdapter,
    "responses": ResponsesVisionAdapter,
    "gemini-interactions": GeminiInteractionsAdapter,
}

# 文档与配置校验共用同一份来源
SUPPORTED_PROVIDERS: tuple[str, ...] = tuple(ADAPTERS)


def normalize_provider(provider: str | None = None) -> str:
    """归一化 provider 名；``None`` 落到 ``settings.vision_provider``。"""
    return (provider or settings.vision_provider).lower().strip()


def create_vision_adapter(
    model_override: str | None = None,
    provider: str | None = None,
) -> VisionAdapter:
    """按 provider 创建对应视觉适配器实例。

    Args:
        model_override: 可选的模型名称覆盖；未指定时使用该后端的配置默认值。
        provider: 可选的视觉后端覆盖；未指定时使用 ``settings.vision_provider``。
            ``extract_text`` 用它按 ``settings.active_ocr_backend`` 指定 OCR 后端。

    Returns:
        :class:`VisionAdapter` 具体实例。

    Raises:
        ValueError: 不支持的 provider。
    """
    key = normalize_provider(provider)
    try:
        adapter_cls = ADAPTERS[key]
    except KeyError:
        raise ValueError(
            f"不支持的视觉后端: {key!r}，可选：{' / '.join(SUPPORTED_PROVIDERS)}"
        ) from None
    return adapter_cls(model=model_override)
