from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock


class TokenBucket:
    """Thread-safe token bucket rate limiter."""

    def __init__(
        self,
        *,
        rate: float,
        capacity: float,
        tokens: float | None = None,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if tokens is not None and tokens < 0:
            raise ValueError("tokens must be non-negative")

        self.rate = float(rate)
        self.capacity = float(capacity)
        self._tokens = min(float(capacity if tokens is None else tokens), self.capacity)
        self._timer = timer
        self._last_refill = timer()
        self._lock = Lock()

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def consume(self, tokens: float = 1.0) -> bool:
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        with self._lock:
            self._refill()
            if tokens > self.capacity or self._tokens < tokens:
                return False

            self._tokens -= tokens
            return True

    def try_consume(self, tokens: float = 1.0) -> bool:
        return self.consume(tokens)

    def wait_time(self, tokens: float = 1.0) -> float:
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        with self._lock:
            self._refill()
            if tokens > self.capacity:
                return float("inf")
            if self._tokens >= tokens:
                return 0.0
            return (tokens - self._tokens) / self.rate

    def _refill(self) -> None:
        now = self._timer()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_refill = now
