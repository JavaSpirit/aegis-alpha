from __future__ import annotations

from aegis_alpha.measurements.orderflow_proxy import simulate_historical_orderflow_proxy
from aegis_alpha.models import MinuteReplayBar, MinuteReplaySnapshot


def test_simulate_historical_orderflow_proxy_flags_volume_spikes() -> None:
    snapshot = MinuteReplaySnapshot(
        symbol="002281",
        name="光迅科技",
        timestamp="2026-06-18T10:00:00+08:00",
        trading_day="2026-06-18",
        bars=[
            MinuteReplayBar(time="09:31", last_price=10.0, volume=100.0),
            MinuteReplayBar(time="09:32", last_price=10.1, volume=100.0),
            MinuteReplayBar(time="09:33", last_price=10.2, volume=100.0),
            MinuteReplayBar(time="09:37", last_price=10.8, volume=220.0),
            MinuteReplayBar(time="09:41", last_price=10.9, volume=260.0),
            MinuteReplayBar(time="10:01", last_price=10.7, volume=500.0),
        ],
    )

    result = simulate_historical_orderflow_proxy(
        snapshot,
        window_start="09:31",
        window_end="10:00",
        volume_ratio_threshold=1.5,
    )

    assert result["data_mode"] == "historical_minute_volume_proxy"
    assert result["can_compute_big_order_buy_ratio"] is False
    assert result["active_trade_side_available"] is False
    assert result["baseline_volume"] == 100.0
    assert result["spike_minute_count"] == 2
    assert result["first_spike_time"] == "09:37"
    assert result["max_volume_ratio"] == 2.6


def test_simulate_historical_orderflow_proxy_marks_missing_bars() -> None:
    snapshot = MinuteReplaySnapshot(
        symbol="002281",
        timestamp="2026-06-18T10:00:00+08:00",
        trading_day="2026-06-18",
        bars=[],
    )

    result = simulate_historical_orderflow_proxy(snapshot)

    assert result["data_mode"] == "unavailable"
    assert result["error"] == "missing_minute_bars"
    assert result["can_compute_big_order_buy_ratio"] is False
