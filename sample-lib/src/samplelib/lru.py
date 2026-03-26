from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class CacheStats:
    hits: int = 0
    misses: int = 0


class LRUCache(Generic[K, V]):
    """A simple thread-safe LRU cache.

    This implementation is intentionally small but realistic enough for review testing.
    """

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = capacity
        self._data: "OrderedDict[K, V]" = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(hits=self._hits, misses=self._misses)

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            if key not in self._data:
                self._misses += 1
                return None

            self._hits += 1
            value = self._data.pop(key)
            self._data[key] = value  # mark as most-recently-used
            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._data:
                self._data.pop(key)
            self._data[key] = value

            if len(self._data) > self._capacity:
                self._data.popitem(last=False)  # evict least-recently-used

    def get_or_set(self, key: K, factory: Callable[[], V]) -> V:
        """Get a cached value or create/store it."""
        existing = self.get(key)
        if existing is not None:
            return existing

        value = factory()
        self.set(key, value)
        return value
