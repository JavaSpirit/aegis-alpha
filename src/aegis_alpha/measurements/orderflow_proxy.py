from __future__ import annotations

from typing import Any

from aegis_alpha.models import MinuteReplayBar, MinuteReplaySnapshot


def simulate_historical_orderflow_proxy(
    snapshot: MinuteReplaySnapshot,
    *,
    window_start: str = "",
    window_end: str = "",
    baseline_window: int = 3,
    volume_ratio_threshold: float = 1.5,
) -> dict[str, Any]:
    """Simulate weak order-flow activity from historical minute volume.

    This cannot recover tick-level large trades or active buy/sell direction.
    It only identifies minute bars whose volume is elevated versus the opening
    baseline, so agents have a conservative proxy instead of inventing Level-2.
    """
    bars = _windowed_bars(snapshot.bars, window_start=window_start, window_end=window_end)
    if not bars:
        return {
            "symbol": snapshot.symbol,
            "trading_day": snapshot.trading_day,
            "data_mode": "unavailable",
            "proxy_source": "minute_volume",
            "error": "missing_minute_bars",
            "can_compute_big_order_buy_ratio": False,
            "active_trade_side_available": False,
        }

    safe_baseline_window = max(1, min(int(baseline_window or 3), len(bars)))
    baseline_bars = bars[:safe_baseline_window]
    baseline_volume = sum(bar.volume for bar in baseline_bars) / len(baseline_bars)
    threshold = max(0.0, float(volume_ratio_threshold or 1.5))
    spike_bars = [
        {
            "time": bar.time,
            "price": bar.last_price,
            "volume": bar.volume,
            "volume_ratio": _volume_ratio(bar.volume, baseline_volume),
        }
        for bar in bars
        if baseline_volume > 0 and _volume_ratio(bar.volume, baseline_volume) >= threshold
    ]
    max_bar = max(bars, key=lambda bar: _volume_ratio(bar.volume, baseline_volume))
    return {
        "symbol": snapshot.symbol,
        "name": snapshot.name,
        "trading_day": snapshot.trading_day,
        "data_mode": "historical_minute_volume_proxy",
        "proxy_source": "minute_volume",
        "window": {"start": window_start, "end": window_end},
        "minute_count": len(bars),
        "baseline_window": safe_baseline_window,
        "baseline_volume": round(baseline_volume, 2),
        "volume_ratio_threshold": threshold,
        "active_trade_side_available": False,
        "can_compute_big_order_buy_ratio": False,
        "spike_minute_count": len(spike_bars),
        "spike_minutes": spike_bars[:20],
        "first_spike_time": spike_bars[0]["time"] if spike_bars else "",
        "last_spike_time": spike_bars[-1]["time"] if spike_bars else "",
        "max_volume_ratio": _volume_ratio(max_bar.volume, baseline_volume),
        "max_volume_time": max_bar.time,
        "notes": [
            "Historical simulation uses minute-bar volume only.",
            "It cannot identify tick-level large trades or active buy/sell direction.",
            "Use this as weak盘口活跃度 evidence, not as 主动大单买入占比.",
        ],
    }


def _windowed_bars(
    bars: list[MinuteReplayBar],
    *,
    window_start: str = "",
    window_end: str = "",
) -> list[MinuteReplayBar]:
    return [
        bar
        for bar in bars
        if (not window_start or bar.time >= window_start) and (not window_end or bar.time <= window_end)
    ]


def _volume_ratio(volume: float, baseline_volume: float) -> float:
    return round(volume / baseline_volume, 6) if baseline_volume > 0 else 0.0
