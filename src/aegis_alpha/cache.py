from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from threading import Lock
from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")
_MISSING = object()


class TTLCache(Generic[K, V]):
    """Small thread-safe TTL cache for provider query results."""

    def __init__(
        self,
        ttl_seconds: float,
        *,
        maxsize: int | None = None,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        if maxsize is not None and maxsize <= 0:
            raise ValueError("maxsize must be positive")

        self.ttl_seconds = float(ttl_seconds)
        self.maxsize = maxsize
        self._timer = timer
        self._items: dict[K, tuple[float, V]] = {}
        self._lock = Lock()

    def set(self, key: K, value: V) -> None:
        expires_at = self._timer() + self.ttl_seconds
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = (expires_at, value)
            self._evict_if_needed()

    def get(self, key: K, default: V | None = None) -> V | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return default

            expires_at, value = item
            if self._is_expired(expires_at):
                self._items.pop(key, None)
                return default
            return value

    def pop(self, key: K, default: V | None = None) -> V | None:
        with self._lock:
            item = self._items.pop(key, None)
            if item is None:
                return default

            expires_at, value = item
            if self._is_expired(expires_at):
                return default
            return value

    def delete(self, key: K) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def cleanup(self) -> int:
        with self._lock:
            before = len(self._items)
            self._purge_expired()
            return before - len(self._items)

    def keys(self) -> list[K]:
        with self._lock:
            self._purge_expired()
            return list(self._items.keys())

    def values(self) -> list[V]:
        with self._lock:
            self._purge_expired()
            return [value for _, value in self._items.values()]

    def items(self) -> list[tuple[K, V]]:
        with self._lock:
            self._purge_expired()
            return [(key, value) for key, (_, value) in self._items.items()]

    def __setitem__(self, key: K, value: V) -> None:
        self.set(key, value)

    def __getitem__(self, key: K) -> V:
        value = self.get(key, _MISSING)  # type: ignore[arg-type]
        if value is _MISSING:
            raise KeyError(key)
        return value  # type: ignore[return-value]

    def __contains__(self, key: object) -> bool:
        with self._lock:
            item = self._items.get(key)  # type: ignore[arg-type]
            if item is None:
                return False

            expires_at, _ = item
            if self._is_expired(expires_at):
                self._items.pop(key, None)  # type: ignore[arg-type]
                return False
            return True

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired()
            return len(self._items)

    def __iter__(self) -> Iterator[K]:
        return iter(self.keys())

    def _is_expired(self, expires_at: float) -> bool:
        return self._timer() >= expires_at

    def _purge_expired(self) -> None:
        expired = [key for key, (expires_at, _) in self._items.items() if self._is_expired(expires_at)]
        for key in expired:
            self._items.pop(key, None)

    def _evict_if_needed(self) -> None:
        self._purge_expired()
        if self.maxsize is None:
            return
        while len(self._items) > self.maxsize:
            oldest_key = next(iter(self._items))
            self._items.pop(oldest_key, None)
