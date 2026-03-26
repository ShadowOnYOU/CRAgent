"""samplelib: a tiny library for testing code review tooling."""

from .lru import LRUCache
from .text import normalize_whitespace

__all__ = ["LRUCache", "normalize_whitespace"]
