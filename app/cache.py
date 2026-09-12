"""问答结果缓存。

演示和评测里同一个问题会被反复问。v1 每次都完整走一遍 LLM，纯属浪费。

缓存 key 里除了问题本身，还必须带上**会影响答案的一切**：
schema 指纹、模型名、快路径开关。少带一个，改完配置之后拿到的就是旧答案，
而且这种错误极难发现 —— 你以为改动没生效，其实是缓存在骗你。

评测默认关掉缓存（`--cache` 才开）：否则重复轮次跑出来的方差恒等于 0，
"多轮取中位数"这件事就变成了自欺欺人。
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


def make_key(*parts: Any) -> str:
    blob = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass
class _Entry:
    value: Any
    born: float


class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: float = 3600.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: OrderedDict[str, _Entry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            self.misses += 1
            return None
        if self.ttl > 0 and time.time() - entry.born > self.ttl:
            del self._data[key]
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: Any) -> None:
        self._data[key] = _Entry(value, time.time())
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
        self.hits = self.misses = 0

    def stats(self) -> str:
        total = self.hits + self.misses
        rate = f"{self.hits / total:.0%}" if total else "-"
        return f"{len(self._data)} 条 / 命中 {self.hits}/{total} ({rate})"
