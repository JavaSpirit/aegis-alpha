from __future__ import annotations

import pytest

from aegis_alpha.measurements.minute_bars import rolling_points_to_minute_bars
from aegis_alpha.models import MinuteReplayBar


# ---------------------------------------------------------------------------
# Shared fixture: 3 points in 09:31 + 2 points in 09:32
# Prices: 10.0, 10.2, 10.1  /  10.3, 10.5
# Cumulative turnover: 1000, 1500, 1800  /  2000, 2600
# ---------------------------------------------------------------------------
def _two_minute_points() -> list[tuple[str, float, float]]:
    return [
        ("2024-03-01T09:31:05", 10.0, 1000.0),
        ("2024-03-01T09:31:30", 10.2, 1500.0),
        ("2024-03-01T09:31:55", 10.1, 1800.0),
        ("2024-03-01T09:32:10", 10.3, 2000.0),
        ("2024-03-01T09:32:50", 10.5, 2600.0),
    ]


class TestCumulativeMode:
    """turnover_is_cumulative=True (default): volume = delta between minute ends."""

    def test_returns_two_bars(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points())
        assert len(bars) == 2

    def test_bar_types(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points())
        for bar in bars:
            assert isinstance(bar, MinuteReplayBar)

    def test_last_prices(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points())
        assert bars[0].last_price == 10.1
        assert bars[1].last_price == 10.5

    def test_time_format_hhmm(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points())
        assert bars[0].time == "09:31"
        assert bars[1].time == "09:32"

    def test_first_bar_volume_is_zero(self) -> None:
        """First bar has no prior-minute baseline, so volume is 0.0 by design
        (avoids a spurious huge spike from the full-morning cumulative amount)."""
        bars = rolling_points_to_minute_bars(_two_minute_points())
        assert bars[0].volume == 0.0

    def test_second_bar_volume_is_delta(self) -> None:
        """09:32 volume = last_cumulative_in_09:32 - last_cumulative_in_09:31 = 2600 - 1800 = 800."""
        bars = rolling_points_to_minute_bars(_two_minute_points())
        assert bars[1].volume == pytest.approx(800.0)

    def test_chronological_order(self) -> None:
        """Output order follows minute progression, even if input is shuffled."""
        shuffled = list(reversed(_two_minute_points()))
        bars = rolling_points_to_minute_bars(shuffled)
        assert bars[0].time == "09:31"
        assert bars[1].time == "09:32"


class TestPerTickMode:
    """turnover_is_cumulative=False: volume = sum of per-point turnover amounts."""

    def test_first_bar_volume_sum(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points(), turnover_is_cumulative=False)
        assert bars[0].volume == pytest.approx(1000.0 + 1500.0 + 1800.0)

    def test_second_bar_volume_sum(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points(), turnover_is_cumulative=False)
        assert bars[1].volume == pytest.approx(2000.0 + 2600.0)

    def test_returns_two_bars(self) -> None:
        bars = rolling_points_to_minute_bars(_two_minute_points(), turnover_is_cumulative=False)
        assert len(bars) == 2


class TestEdgeCases:
    def test_empty_input(self) -> None:
        assert rolling_points_to_minute_bars([]) == []

    def test_single_point_cumulative(self) -> None:
        bars = rolling_points_to_minute_bars([("2024-03-01T10:00:01", 9.5, 500.0)])
        assert len(bars) == 1
        assert isinstance(bars[0], MinuteReplayBar)
        assert bars[0].last_price == 9.5
        assert bars[0].time == "10:00"
        # First (and only) bar — no prior baseline → volume = 0.0
        assert bars[0].volume == 0.0

    def test_single_point_per_tick(self) -> None:
        bars = rolling_points_to_minute_bars(
            [("2024-03-01T10:00:01", 9.5, 500.0)],
            turnover_is_cumulative=False,
        )
        assert len(bars) == 1
        assert bars[0].volume == pytest.approx(500.0)

    def test_unparseable_timestamp_skipped(self) -> None:
        """Malformed timestamps are silently dropped; valid points still form bars."""
        points: list[tuple[str, float, float]] = [
            ("NOT_A_TIMESTAMP", 10.0, 100.0),
            ("2024-03-01T09:31:05", 10.5, 200.0),
            ("also-bad", 11.0, 300.0),
        ]
        bars = rolling_points_to_minute_bars(points)
        assert len(bars) == 1
        assert bars[0].last_price == 10.5

    def test_unparseable_only_returns_empty(self) -> None:
        points: list[tuple[str, float, float]] = [
            ("GARBAGE", 10.0, 100.0),
        ]
        assert rolling_points_to_minute_bars(points) == []

    def test_negative_delta_clamped_to_zero(self) -> None:
        """If cumulative turnover decreases (data anomaly), clamp volume to 0."""
        points: list[tuple[str, float, float]] = [
            ("2024-03-01T09:31:05", 10.0, 2000.0),  # minute 09:31, cumulative=2000
            ("2024-03-01T09:32:05", 10.1, 1500.0),  # minute 09:32, cumulative=1500 (anomaly)
        ]
        bars = rolling_points_to_minute_bars(points, turnover_is_cumulative=True)
        assert bars[1].volume == pytest.approx(0.0)

    def test_all_same_minute(self) -> None:
        """Three points all in same minute collapse to one bar."""
        points = [
            ("2024-03-01T09:31:01", 10.0, 100.0),
            ("2024-03-01T09:31:30", 10.5, 200.0),
            ("2024-03-01T09:31:59", 10.3, 300.0),
        ]
        bars = rolling_points_to_minute_bars(points)
        assert len(bars) == 1
        assert bars[0].last_price == 10.3
