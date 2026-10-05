"""OpenEye 配置加载。

基于 pydantic-settings 从环境变量与 ``.env`` 文件加载配置，支持
OpenAI / Gemini / Anthropic / OpenAI Responses / Gemini Interactions
五类视觉后端。

字段与后端的对应关系统一由 :data:`VisionProvider` 与
:mod:`openeye_mcp.vision.registry` 描述，避免「新增一个后端要改多处」
时各处字面量漂移。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 受支持的视觉后端；provider → 适配器类的映射见 vision/registry.py
VisionProvider = Literal[
    "openai", "gemini", "anthropic", "responses", "gemini-interactions"
]

# 仓库根的 .env：MCP 客户端通常以**自己的项目目录**为 cwd 启动 stdio 子进程，
# 只写 ".env" 会让用户在仓库里 cp 出来的 .env 静默不生效（历史缺陷）。
# 因此同时按 cwd 与本文件位置向上查找。
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """OpenEye 全局配置。

    字段命名采用 ``snake_case``，对应环境变量为全大写形式
    （例如 ``vision_provider`` ↔ ``VISION_PROVIDER``）。
    """

    model_config = SettingsConfigDict(
        env_file=(".env", str(_REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 视觉后端提供者：openai / gemini / anthropic / responses / gemini-interactions
    vision_provider: VisionProvider = "openai"

    # ---------- OpenAI 兼容后端 ----------
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    openai_base_url: str = ""

    # ---------- Gemini 后端 ----------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"
    # 接口地址；留空用官方端点。自建代理 / 兼容网关时填这里
    # （历史缺陷：.env.example 提到过该变量但配置类没有对应字段，
    #  pydantic 的 extra="ignore" 会静默丢弃，导致代理配置不生效）
    gemini_base_url: str = ""

    # ---------- Anthropic 后端 ----------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    # ---------- OpenAI Responses API 后端 ----------
    # 走 OpenAI 官方 Responses 协议（/v1/responses），主要用于 OpenAI 官方
    # 及真正实现该协议的端点。第三方 OpenAI 兼容厂商多用 Chat Completions。
    responses_api_key: str = ""
    responses_model: str = "gpt-5.6"
    responses_base_url: str = "https://api.openai.com/v1"

    # ---------- OCR 后端 ----------
    # extract_text 使用的后端；留空（默认）跟随 vision_provider。
    # 历史缺陷：默认值写死 "openai"，但 README 承诺「不填时同 VISION_PROVIDER」，
    # 于是 VISION_PROVIDER=gemini 时 OCR 悄悄走了另一个后端且要另一份 Key。
    ocr_backend: VisionProvider | None = None

    # ---------- 性能优化 ----------
    # 图片预处理：最大边长，超过则等比缩放后转 JPEG；0 表示禁用预处理
    image_max_dim: int = 2048
    # 结果缓存开关
    cache_enabled: bool = True
    # 缓存最大条目数（LRU 淘汰）
    cache_max_size: int = 128
    # 缓存存活秒数（TTL）
    cache_ttl: int = 3600
    # 已解析图片的「来源级」缓存存活秒数；0 表示每次都重新取图
    image_cache_ttl: int = 300
    # 已解析图片缓存的最大条目数（按来源路径 / URL / data URI 指纹计）
    image_cache_max_size: int = 8

    # ---------- 网络请求 ----------
    # 视觉后端 HTTP 请求超时（秒）
    request_timeout: float = 120.0
    # 单次工具调用的总时间预算（秒）。外层重试 × 降级请求 × 内层重试会把
    # 最坏耗时相乘到几十分钟，远超客户端超时；0 表示不设预算。
    request_deadline: float = 300.0
    # 失败重试次数（对网络/超时错误与 429/5xx 重试；400/401/403/404 不重试）
    max_retries: int = 3
    # 重试退避基数（秒），第 n 次重试等待 retry_backoff * 2**(n-1) 再加抖动；
    # 设为 0 可关闭退避（测试用）
    retry_backoff: float = 0.5
    # 视觉模型返回的最大 token 数（推理模型需更大预算，否则 content 被截断为空）
    max_tokens: int = 4096
    # 推理深度：low / medium / high；留空则不发送该参数（部分后端不支持）
    reasoning_effort: Literal["", "low", "medium", "high"] = ""
    # 日志级别（loguru，输出到 stderr）；DEBUG 会把入参摘要写全
    log_level: str = "INFO"

    # ---------- 图片 URL 下载 ----------
    # 下载图片的最大字节数，超过则拒绝（防止内存耗尽）
    max_image_bytes: int = 20 * 1024 * 1024
    # 是否允许访问内网/保留地址（默认禁止，防止 SSRF；仅本地调试时设为 true）
    allow_private_urls: bool = False
    # 逗号分隔的本地目录白名单；非空时本地图片路径必须落在其中之一内。
    # 默认空 = 不限制目录，但仍强制校验内容确实是可解码的图片。
    allowed_image_roots: str = ""

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        """日志级别大小写不敏感，且非法值直接报错而非静默降级。"""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @property
    def active_ocr_backend(self) -> VisionProvider:
        """``extract_text`` 实际使用的后端：显式配置优先，否则跟随主后端。"""
        return self.ocr_backend or self.vision_provider

    @property
    def image_roots(self) -> list[Path]:
        """解析 :attr:`allowed_image_roots` 为绝对路径列表；空配置返回 ``[]``。"""
        return [
            Path(item.strip()).expanduser().resolve()
            for item in self.allowed_image_roots.split(",")
            if item.strip()
        ]


settings = Settings()
