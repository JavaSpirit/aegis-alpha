from __future__ import annotations

from aegis_alpha.measurements.trend_outcome import summarize_trend_window_outcome
from aegis_alpha.models import MinuteReplayBar, MinuteReplaySnapshot


def _snapshot(prices: list[tuple[str, float]], previous_close: float = 10.0) -> MinuteReplaySnapshot:
    return MinuteReplaySnapshot(
        symbol="002281",
        timestamp="2026-06-18T10:00:00+08:00",
        trading_day="2026-06-18",
        previous_close=previous_close,
        bars=[
            MinuteReplayBar(time=time, last_price=price, average_price=price, volume=100_000)
            for time, price in prices
        ],
    )


def test_trend_outcome_labels_morning_followthrough() -> None:
    result = summarize_trend_window_outcome(
        _snapshot([("09:31", 10.1), ("09:41", 10.5), ("10:00", 10.35)])
    )

    assert result["data_mode"] == "trend_window_outcome"
    assert result["max_gain_pct"] == 5.0
    assert result["window_end_pct"] == 3.5
    assert result["morning_followthrough"] is True
    assert result["outcome_label"] == "morning_followthrough"


def test_trend_outcome_labels_gap_and_fade() -> None:
    result = summarize_trend_window_outcome(
        _snapshot([("09:31", 10.5), ("09:33", 10.8), ("10:00", 10.1)])
    )

    assert result["window_open_pct"] == 5.0
    assert result["drawdown_after_high_pct"] == -6.4815
    assert result["gap_and_fade"] is True
    assert result["outcome_label"] == "gap_and_fade"


def test_trend_outcome_marks_missing_previous_close() -> None:
    result = summarize_trend_window_outcome(
        _snapshot([("09:31", 10.5)], previous_close=0.0)
    )

    assert result["data_mode"] == "unavailable"
    assert result["error"] == "missing_previous_close"
