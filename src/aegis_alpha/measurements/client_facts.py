from __future__ import annotations

import math


def avg_turnover_10d(daily_turnovers: list[float]) -> float:
    """Mean turnover over the last 10 sessions (fewer if the series is short)."""
    if not daily_turnovers:
        return 0.0
    window = daily_turnovers[-10:]
    return round(sum(window) / len(window), 6)


def _ma5_series(prices: list[float]) -> list[float]:
    if len(prices) < 5:
        return []
    return [sum(prices[i - 5 : i]) / 5 for i in range(5, len(prices) + 1)]


def ma5_slope_degrees(prices: list[float]) -> float:
    """Angle (degrees) of the 5-day moving average over its last two points.

    The x-step is normalized to one trading day. This is a pure measurement
    convention, NOT a threshold judgment — the client's 30-60 degree test
    belongs to the agent/strategy-prior layer, not here.
    """
    ma5 = _ma5_series(prices)
    if len(ma5) < 2:
        return 0.0
    delta = ma5[-1] - ma5[-2]
    base = abs(ma5[-2]) or 1.0
    return round(math.degrees(math.atan2(delta / base, 1.0 / len(ma5))), 4)


def prev_day_volume_shrink_ratio(*, prev_day_volume: float, avg_10d: float) -> float:
    """T-1 volume relative to the 10-day average. Below 1.0 means it shrank."""
    if avg_10d <= 0.0:
        return 0.0
    return round(prev_day_volume / avg_10d, 6)


def broke_previous_high(*, current_price: float, prior_highs: list[float]) -> bool:
    """True if the current price exceeds the maximum of prior session highs."""
    if not prior_highs:
        return False
    return current_price > max(prior_highs)
