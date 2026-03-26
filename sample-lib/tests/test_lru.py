from __future__ import annotations

from samplelib.lru import LRUCache


def test_lru_eviction() -> None:
    cache: LRUCache[str, int] = LRUCache(capacity=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_marks_recent_on_get() -> None:
    cache: LRUCache[str, int] = LRUCache(capacity=2)
    cache.set("a", 1)
    cache.set("b", 2)

    assert cache.get("a") == 1
    cache.set("c", 3)

    # b should be evicted, because a was recently used
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
