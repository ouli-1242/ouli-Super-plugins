"""视觉适配器抽象基类与共用装配。

各后端的真实差异只有两处：payload 构造、响应解析。(模型 / Key / 端点)
三元组的解析、生成参数的默认值兜底、Bearer 认证头这三件事五个后端完全
同形，原先各抄一份且**兜底并不一致**——``gemini`` 与 ``gemini-interactions``
漏掉了 ``max_tokens`` 的配置默认值回退，导致布局/表格请求的 8192 与
配置默认值双双失效。统一走 :meth:`VisionOptions.resolve` 后不再可能漏。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from openeye_mcp.config import settings


@dataclass(frozen=True)
class VisionOptions:
    """一次视觉请求的生成参数；构造时已把 ``None`` 解析成配置默认值。"""

    max_tokens: int
    reasoning_effort: str | None
    response_format: dict | None

    @classmethod
    def resolve(
        cls,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        response_format: dict | None = None,
    ) -> VisionOptions:
        """按「显式参数优先，缺省回落 ``settings``」解析一次请求的生成参数。"""
        return cls(
            max_tokens=settings.max_tokens if max_tokens is None else max_tokens,
            reasoning_effort=reasoning_effort or settings.reasoning_effort or None,
            response_format=response_format,
        )

    @property
    def wants_json(self) -> bool:
        """是否要求 JSON 输出（上游以 ``{"type": "json_object"}`` 表达）。"""
        if not self.response_format:
            return False
        return self.response_format.get("type") == "json_object"


class VisionAdapter(ABC):
    """视觉理解适配器抽象基类。

    子类只需声明两个类属性，即可复用端点解析与认证头：

    - :attr:`settings_prefix` —— 配置字段前缀（``openai`` 对应
      ``openai_model`` / ``openai_api_key`` / ``openai_base_url``）
    - :attr:`default_base_url` —— 配置留空时使用的官方端点

    上层工具只依赖 :meth:`describe` 与 :meth:`describe_text`，后端可插拔。
    """

    settings_prefix: str = ""
    default_base_url: str = ""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        prefix = self.settings_prefix
        self.model: str = model or getattr(settings, f"{prefix}_model")
        self.api_key: str = (
            api_key if api_key is not None else getattr(settings, f"{prefix}_api_key")
        )
        base = base_url if base_url is not None else getattr(settings, f"{prefix}_base_url")
        base = (base or "").strip()
        self.base_url: str = base or self.default_base_url

    def bearer_headers(self) -> dict[str, str]:
        """OpenAI 系后端的 JSON + Bearer 认证头。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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
        """对 ``image_b64`` 执行一次「带图 + 提示词 → 文本」请求。

        不只服务「描述」：OCR、视觉问答、布局与表格抽取都经由本方法，
        差别只在传入的 ``prompt`` 与 ``response_format``。

        Args:
            image_b64: 图像的 base64 编码字符串（不含 data URI 前缀）。
            mime_type: 图像 MIME 类型，例如 ``image/png``。
            prompt: 提示词；``None`` 不被允许（server 分发层会剔除 null 并
                交由工具层默认值补全）。
            max_tokens: 输出 token 上限覆盖；None 时用 ``settings.max_tokens``。
            reasoning_effort: 推理深度覆盖；None 时用 ``settings.reasoning_effort``。
            response_format: 输出格式约束（如 ``{"type": "json_object"}``）。

        Returns:
            模型返回的文本结果。
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
