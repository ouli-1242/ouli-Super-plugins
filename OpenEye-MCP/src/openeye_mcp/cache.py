"""缓存：视觉结果 + 已解析图片。

两组缓存解决两件不同的事：

- :class:`VisionCache` —— ``(图片摘要, 提示词, 模型, 参数指纹) → 模型输出``，
  命中即可完全跳过一次后端调用。
- :class:`PreparedImageCache` —— ``来源指纹 → 已下载已预处理的图片``。
  历史缺陷：视觉缓存的 key 需要先解析图片才能算出，于是**命中也要重新下载
  并重新解码**（一次布局分析最坏把同一张图下载 4 次）。这层缓存把下载与
  Pillow 处理也省掉。

``variant`` 必须参与视觉缓存 key：只用 (图片, 提示词, 模型) 时，切换
``VISION_PROVIDER`` / ``OCR_BACKEND`` 或改动生成参数后会命中旧结果的
历史缺陷。指纹由调用方以 JSON 生成（见 ``tools._cache_variant``），
不再用 ``|`` 拼接字符串——拼接串在参数含分隔符时会串键。
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from openeye_mcp.config import settings


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
        self._store: OrderedDict[
            tuple[str, str, str, str], tuple[str, float]
        ] = OrderedDict()
        self._hits = 0
        self._misses = 0
        # 时间戳获取函数，便于测试注入（默认使用 time.monotonic）
        self._now = time.monotonic

    @staticmethod
    def _make_key(
        image_hash: str, prompt: str, model: str, variant: str = ""
    ) -> tuple[str, str, str, str]:
        """构造缓存 key（含真实模型名与参数指纹 ``variant``）。"""
        return (image_hash, prompt, model, variant)

    def get(
        self, image_hash: str, prompt: str, model: str, variant: str = ""
    ) -> str | None:
        """查缓存，TTL 过期或未命中返回 ``None``。"""
        key = self._make_key(image_hash, prompt, model, variant)
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

    def set(
        self,
        image_hash: str,
        prompt: str,
        model: str,
        text: str,
        variant: str = "",
    ) -> None:
        """写入缓存；容量超限时淘汰最旧条目。"""
        key = self._make_key(image_hash, prompt, model, variant)
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


@dataclass(frozen=True)
class PreparedImage:
    """已完成下载、预处理并算好摘要的一张图。"""

    b64: str
    mime: str
    digest: str

    @property
    def nbytes(self) -> int:
        return len(self.b64)


class PreparedImageCache:
    """按「来源指纹」缓存已解析图片，受条目数与总字节双重限制。

    base64 图片动辄数 MB，只按条目数淘汰会在几张超大图下把内存顶满，
    因此超过字节预算的条目直接不缓存（交给上层的视觉结果缓存）。
    """

    # 单条目字节预算：超过此值不入缓存（约对应 24 MB 原图）
    _MAX_ENTRY_BYTES = 32 * 1024 * 1024

    def __init__(
        self,
        max_size: int | None = None,
        ttl: int | None = None,
        max_total_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self._max_size = max_size if max_size is not None else settings.image_cache_max_size
        self._ttl = ttl if ttl is not None else settings.image_cache_ttl
        self._max_total_bytes = max_total_bytes
        self._store: OrderedDict[str, tuple[PreparedImage, float]] = OrderedDict()
        self._total_bytes = 0
        self._now: Callable[[], float] = time.monotonic

    def get(self, fingerprint: str) -> PreparedImage | None:
        if self._ttl <= 0:
            return None
        entry = self._store.get(fingerprint)
        if entry is None:
            return None
        image, ts = entry
        if (self._now() - ts) > self._ttl:
            self._drop(fingerprint)
            return None
        self._store.move_to_end(fingerprint)
        return image

    def set(self, fingerprint: str, image: PreparedImage) -> None:
        if self._ttl <= 0 or image.nbytes > self._MAX_ENTRY_BYTES:
            return
        self._store[fingerprint] = (image, self._now())
        self._store.move_to_end(fingerprint)
        self._total_bytes += image.nbytes
        self._trim()

    def _drop(self, fingerprint: str) -> None:
        entry = self._store.pop(fingerprint, None)
        if entry is not None:
            self._total_bytes -= entry[0].nbytes

    def _trim(self) -> None:
        while len(self._store) > self._max_size:
            self._drop(next(iter(self._store)))
        while self._store and self._total_bytes > self._max_total_bytes:
            self._drop(next(iter(self._store)))

    def clear(self) -> None:
        self._store.clear()
        self._total_bytes = 0


def source_fingerprint(image_source: str) -> str:
    """给图片来源算一个「内容变了就会变」的缓存键。

    - 本地路径：``mtime + size``，文件被覆盖后不会命中旧内容
    - URL：地址本身（内容可能变，靠 TTL 兜底）
    - data URI：源串就是内容，取哈希避免用数 MB 字符串当 key
    """
    if image_source.startswith("data:"):
        return "data:" + hashlib.sha256(image_source.encode()).hexdigest()[:32]
    if image_source.startswith(("http://", "https://")):
        return "url:" + hashlib.sha256(image_source.encode()).hexdigest()[:32]
    try:
        stat = Path(image_source).stat()
        return f"file:{image_source}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        return "file:" + hashlib.sha256(image_source.encode()).hexdigest()[:32]


# 模块级单例，供 tools 复用
vision_cache = VisionCache()
prepared_image_cache = PreparedImageCache()
