"""视觉识别结果缓存。

基于 ``OrderedDict`` 实现 LRU + TTL 的内存缓存，避免对相同
(图片哈希, 提示词, 模型) 三元组重复调用视觉后端。

缓存操作均为内存操作，无需异步；通过模块级单例
:data:`vision_cache` 在 :func:`deepeye_mcp.tools._run_vision` 中复用。
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import NamedTuple

from deepeye_mcp.config import settings


class _CacheStats(NamedTuple):
    """缓存命中统计。"""

    hits: int
    misses: int


class VisionCache:
    """视觉识别结果 LRU + TTL 缓存。

    - 容量达 ``settings.cache_max_size`` 上限时淘汰最旧条目（LRU）。
    - 每条目记录写入时间戳，超过 ``settings.cache_ttl`` 秒视为未命中（TTL）。
    - ``get`` 命中时将条目移至队尾（最近使用），未命中或过期时删除并返回 ``None``。
    """

    def __init__(
        self,
        max_size: int | None = None,
        ttl: int | None = None,
    ) -> None:
        # 显式传入参数便于测试；默认从 settings 读取
        self._max_size: int = (
            max_size if max_size is not None else settings.cache_max_size
        )
        self._ttl: int = ttl if ttl is not None else settings.cache_ttl
        # OrderedDict 中 value 为 (text, timestamp)
        self._store: OrderedDict[tuple[str, str, str], tuple[str, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        # 时间戳获取函数，便于测试注入（默认使用 time.monotonic）
        self._now = time.monotonic

    @staticmethod
    def _make_key(image_hash: str, prompt: str, model: str) -> tuple[str, str, str]:
        """构造缓存 key。"""
        return (image_hash, prompt, model)

    def get(self, image_hash: str, prompt: str, model: str) -> str | None:
        """查缓存，TTL 过期或未命中返回 ``None``。"""
        key = self._make_key(image_hash, prompt, model)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        text, ts = entry
        # TTL 过期视为未命中
        if self._ttl > 0 and (self._now() - ts) > self._ttl:
            self._misses += 1
            self._store.pop(key, None)
            return None

        # 命中：移至队尾表示最近使用
        self._store.move_to_end(key)
        self._hits += 1
        return text

    def set(self, image_hash: str, prompt: str, model: str, text: str) -> None:
        """写入缓存；容量超限时淘汰最旧条目。"""
        key = self._make_key(image_hash, prompt, model)
        self._store[key] = (text, self._now())
        # 写入即视为最近使用
        self._store.move_to_end(key)
        # LRU 淘汰
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """清空缓存（不影响统计计数）。"""
        self._store.clear()

    def stats(self) -> _CacheStats:
        """返回命中/未命中计数。"""
        return _CacheStats(hits=self._hits, misses=self._misses)


# 模块级单例，供 tools 复用
vision_cache = VisionCache()
