from __future__ import annotations

import pytest

from aegis_alpha.cache import TTLCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_ttl_cache_returns_value_before_expiry() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=10, timer=clock.monotonic)

    cache.set("answer", 42)

    assert cache.get("answer") == 42
    assert cache["answer"] == 42
    assert "answer" in cache
    assert len(cache) == 1


def test_ttl_cache_expires_values() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=5, timer=clock.monotonic)

    cache["stale"] = 1
    clock.advance(5)

    assert cache.get("stale") is None
    assert "stale" not in cache
    with pytest.raises(KeyError):
        _ = cache["stale"]
    assert len(cache) == 0


def test_ttl_cache_cleanup_returns_removed_count() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=3, timer=clock.monotonic)

    cache.set("a", 1)
    cache.set("b", 2)
    clock.advance(4)

    assert cache.cleanup() == 2
    assert cache.items() == []


def test_ttl_cache_evicts_oldest_when_maxsize_is_exceeded() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, maxsize=2, timer=clock.monotonic)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.items() == [("b", 2), ("c", 3)]


def test_ttl_cache_delete_pop_and_clear() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, timer=clock.monotonic)

    cache.set("a", 1)
    cache.set("b", 2)

    assert cache.pop("a") == 1
    assert cache.pop("missing", 99) == 99
    cache.delete("b")
    assert len(cache) == 0

    cache.set("c", 3)
    cache.clear()
    assert cache.keys() == []


def test_ttl_cache_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        TTLCache(ttl_seconds=-1)
    with pytest.raises(ValueError):
        TTLCache(ttl_seconds=1, maxsize=0)
