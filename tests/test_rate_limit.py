from __future__ import annotations

import math

import pytest

from aegis_alpha.rate_limit import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_token_bucket_consumes_initial_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=1, capacity=2, timer=clock.monotonic)

    assert bucket.consume()
    assert bucket.consume()
    assert not bucket.consume()


def test_token_bucket_refills_over_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=2, capacity=5, tokens=0, timer=clock.monotonic)

    clock.advance(1.5)

    assert bucket.available_tokens == 3
    assert bucket.consume(2)
    assert bucket.available_tokens == 1


def test_token_bucket_caps_refill_at_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=100, capacity=5, tokens=1, timer=clock.monotonic)

    clock.advance(10)

    assert bucket.available_tokens == 5


def test_token_bucket_wait_time_reports_delay() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=2, capacity=5, tokens=1, timer=clock.monotonic)

    assert bucket.wait_time(3) == 1
    assert bucket.wait_time(6) == float("inf")


def test_token_bucket_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=1)
    with pytest.raises(ValueError):
        TokenBucket(rate=1, capacity=0)
    with pytest.raises(ValueError):
        TokenBucket(rate=1, capacity=1, tokens=-1)

    bucket = TokenBucket(rate=1, capacity=1)
    with pytest.raises(ValueError):
        bucket.consume(0)
    with pytest.raises(ValueError):
        bucket.wait_time(-1)


def test_token_bucket_can_report_unfulfillable_request() -> None:
    bucket = TokenBucket(rate=1, capacity=2)

    assert not bucket.try_consume(3)
    assert math.isinf(bucket.wait_time(3))
