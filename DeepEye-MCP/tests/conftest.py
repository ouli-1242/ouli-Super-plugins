"""pytest 全局配置：禁用缓存避免测试间干扰。"""

import pytest

from deepeye_mcp.cache import vision_cache
from deepeye_mcp.config import settings


@pytest.fixture(autouse=True)
def _disable_cache():
    """每个测试前禁用缓存并清空，避免测试间互相干扰。"""
    settings.cache_enabled = False
    vision_cache.clear()
    yield
    vision_cache.clear()


@pytest.fixture(autouse=True)
def _no_retry_backoff():
    """重试退避归零。

    重试逻辑仍会被执行（调用次数、异常类型照旧），但不为等待退避
    拖慢整个测试套件；需要验证退避本身的测试自行覆盖该值。
    """
    original = settings.retry_backoff
    settings.retry_backoff = 0.0
    yield
    settings.retry_backoff = original
