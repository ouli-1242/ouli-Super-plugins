"""``deepeye_mcp.config.Settings`` 单元测试。

覆盖默认值、环境变量覆盖，以及历史缺陷回归：
``.env.example`` 曾提到 ``GEMINI_BASE_URL``，但配置类没有对应字段，
pydantic 的 ``extra="ignore"`` 会静默丢弃，导致自建代理/兼容网关配置
完全不生效。
"""

from __future__ import annotations

from deepeye_mcp.config import Settings, settings


def test_defaults_are_empty_for_all_api_keys():
    """所有密钥字段默认必须为空——不得内置任何真实凭据。"""
    config = Settings(_env_file=None)

    assert config.openai_api_key == ""
    assert config.gemini_api_key == ""
    assert config.anthropic_api_key == ""
    assert config.responses_api_key == ""


def test_default_values():
    config = Settings(_env_file=None)

    assert config.vision_provider == "openai"
    assert config.ocr_backend == "openai"
    assert config.max_retries == 3
    assert config.retry_backoff == 0.5
    assert config.request_timeout == 120.0
    assert config.allow_private_urls is False
    assert config.max_image_bytes == 20 * 1024 * 1024
    assert config.gemini_base_url == ""


def test_env_override(monkeypatch):
    monkeypatch.setenv("GEMINI_BASE_URL", "https://proxy.example.com/v1beta")
    monkeypatch.setenv("RETRY_BACKOFF", "1.5")
    monkeypatch.setenv("MAX_RETRIES", "1")

    config = Settings(_env_file=None)

    assert config.gemini_base_url == "https://proxy.example.com/v1beta"
    assert config.retry_backoff == 1.5
    assert config.max_retries == 1


def test_gemini_base_url_reaches_both_gemini_adapters(monkeypatch):
    """GEMINI_BASE_URL 必须真正透传到两个 Gemini 适配器（回归）。"""
    from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter
    from deepeye_mcp.vision.gemini_interactions_adapter import (
        GeminiInteractionsAdapter,
    )

    monkeypatch.setattr(
        settings, "gemini_base_url", "https://proxy.example.com/v1beta"
    )

    assert (
        GeminiVisionAdapter(model="m", api_key="k").base_url
        == "https://proxy.example.com/v1beta"
    )
    assert (
        GeminiInteractionsAdapter(model="m", api_key="k").base_url
        == "https://proxy.example.com/v1beta"
    )


def test_explicit_base_url_argument_wins(monkeypatch):
    """显式传入的 base_url 优先级高于配置。"""
    from deepeye_mcp.vision.gemini_adapter import GeminiVisionAdapter

    monkeypatch.setattr(settings, "gemini_base_url", "https://from-settings/v1beta")

    adapter = GeminiVisionAdapter(
        model="m", api_key="k", base_url="https://explicit/v1beta"
    )

    assert adapter.base_url == "https://explicit/v1beta"
