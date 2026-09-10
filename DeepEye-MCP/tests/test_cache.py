"""``deepeye_mcp.cache.VisionCache`` 单元测试。

覆盖：命中 / 未命中 / TTL 过期 / LRU 淘汰 / clear / stats。
通过注入可控时钟函数避免真实 ``time.sleep``。
"""

from __future__ import annotations

import pytest

from deepeye_mcp.cache import VisionCache


class _FakeClock:
    """可控单调时钟，单位：秒。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# 命中 / 未命中
# ---------------------------------------------------------------------------


def test_cache_hit_returns_cached_text():
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("hash1", "prompt1", "model1", "hello world")

    assert cache.get("hash1", "prompt1", "model1") == "hello world"


def test_cache_miss_returns_none():
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("hash1", "prompt1", "model1", "cached")

    # 任意一项不匹配都应未命中
    assert cache.get("hash1", "different-prompt", "model1") is None
    assert cache.get("different-hash", "prompt1", "model1") is None
    assert cache.get("hash1", "prompt1", "different-model") is None


def test_cache_get_empty_cache_returns_none():
    cache = VisionCache(max_size=10, ttl=3600)
    assert cache.get("any", "any", "any") is None


# ---------------------------------------------------------------------------
# TTL 过期
# ---------------------------------------------------------------------------


def test_cache_ttl_expired_returns_none():
    clock = _FakeClock(start=1000.0)
    cache = VisionCache(max_size=10, ttl=100)
    cache._now = clock  # 注入可控时钟

    cache.set("hash1", "prompt1", "model1", "cached-text")

    # 未过期：命中
    clock.advance(50)
    assert cache.get("hash1", "prompt1", "model1") == "cached-text"

    # 过期：返回 None
    clock.advance(60)  # 总共 110 秒 > 100 秒 TTL
    assert cache.get("hash1", "prompt1", "model1") is None


def test_cache_ttl_zero_never_expires():
    """TTL=0 表示永不过期。"""
    clock = _FakeClock(start=1000.0)
    cache = VisionCache(max_size=10, ttl=0)
    cache._now = clock

    cache.set("hash1", "prompt1", "model1", "long-lived")
    clock.advance(1_000_000)  # 极长时间

    assert cache.get("hash1", "prompt1", "model1") == "long-lived"


# ---------------------------------------------------------------------------
# LRU 淘汰
# ---------------------------------------------------------------------------


def test_cache_lru_evicts_oldest_when_capacity_exceeded():
    cache = VisionCache(max_size=2, ttl=3600)

    cache.set("h1", "p1", "m1", "text1")
    cache.set("h2", "p2", "m2", "text2")
    # 容量达上限，再写入应淘汰 h1
    cache.set("h3", "p3", "m3", "text3")

    assert cache.get("h1", "p1", "m1") is None  # 被淘汰
    assert cache.get("h2", "p2", "m2") == "text2"
    assert cache.get("h3", "p3", "m3") == "text3"


def test_cache_lru_access_updates_recency():
    """访问（get）旧条目应刷新其 recency，避免被淘汰。"""
    cache = VisionCache(max_size=2, ttl=3600)

    cache.set("h1", "p1", "m1", "text1")
    cache.set("h2", "p2", "m2", "text2")

    # 访问 h1，使其成为最近使用
    assert cache.get("h1", "p1", "m1") == "text1"

    # 写入 h3，应淘汰最旧的 h2（而非 h1）
    cache.set("h3", "p3", "m3", "text3")

    assert cache.get("h1", "p1", "m1") == "text1"  # 因 get 刷新而保留
    assert cache.get("h2", "p2", "m2") is None  # 被淘汰
    assert cache.get("h3", "p3", "m3") == "text3"


def test_cache_lru_set_updates_recency():
    """对已有 key 重新 set 应刷新其 recency。"""
    cache = VisionCache(max_size=2, ttl=3600)

    cache.set("h1", "p1", "m1", "text1")
    cache.set("h2", "p2", "m2", "text2")
    # 重新写入 h1，刷新 recency
    cache.set("h1", "p1", "m1", "text1-updated")
    # 写入 h3，应淘汰 h2
    cache.set("h3", "p3", "m3", "text3")

    assert cache.get("h1", "p1", "m1") == "text1-updated"
    assert cache.get("h2", "p2", "m2") is None


# ---------------------------------------------------------------------------
# clear / stats
# ---------------------------------------------------------------------------


def test_cache_clear_empties_entries():
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h1", "p1", "m1", "text1")
    cache.set("h2", "p2", "m2", "text2")

    cache.clear()

    assert cache.get("h1", "p1", "m1") is None
    assert cache.get("h2", "p2", "m2") is None


def test_cache_stats_counts_hits_and_misses():
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h1", "p1", "m1", "text1")

    # 1 次命中
    cache.get("h1", "p1", "m1")
    # 2 次未命中
    cache.get("h1", "p2", "m1")
    cache.get("h2", "p1", "m1")

    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 2


def test_cache_stats_counts_ttl_expired_as_miss():
    """TTL 过期应计入未命中。"""
    clock = _FakeClock(start=1000.0)
    cache = VisionCache(max_size=10, ttl=100)
    cache._now = clock

    cache.set("h1", "p1", "m1", "text1")
    clock.advance(200)  # 过期
    cache.get("h1", "p1", "m1")

    stats = cache.stats()
    assert stats.hits == 0
    assert stats.misses == 1


# ---------------------------------------------------------------------------
# variant：后端 + 生成参数指纹
# 回归：历史上 key 只有 (图片, 提示词, 模型)，切换 VISION_PROVIDER /
# OCR_BACKEND 或改动生成参数后会命中旧后端的旧结果。
# ---------------------------------------------------------------------------


def test_cache_different_variant_does_not_hit():
    """variant 不同必须视为未命中。"""
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h", "p", "m", "openai 的结果", variant="openai|4096||")

    assert cache.get("h", "p", "m", variant="anthropic|4096||") is None
    assert cache.get("h", "p", "m", variant="openai|4096||") == "openai 的结果"


def test_cache_same_variant_hits():
    """variant 一致时正常命中。"""
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h", "p", "m", "text", variant="openai|8192|low|{\"type\": \"json_object\"}")

    assert (
        cache.get("h", "p", "m", variant="openai|8192|low|{\"type\": \"json_object\"}")
        == "text"
    )


def test_cache_variant_defaults_to_empty():
    """不传 variant 时行为与历史一致（等价于空指纹）。"""
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h", "p", "m", "text")

    assert cache.get("h", "p", "m") == "text"


def test_cache_max_tokens_difference_is_isolated():
    """仅 max_tokens 不同也不得复用结果。"""
    cache = VisionCache(max_size=10, ttl=3600)
    cache.set("h", "p", "m", "短输出", variant="openai|1024||")

    assert cache.get("h", "p", "m", variant="openai|8192||") is None
