"""Aggregate rolling tick points into per-minute MinuteReplayBar objects.

TURNOVER SEMANTICS — LOAD-BEARING ASSUMPTION
============================================
jvQuant's ``lv1.amount`` (and ``lv10.amount``) is the **cumulative intraday
turnover** (累计成交额, CNY) at the moment of the push — a monotonically
non-decreasing level that resets to 0 at market open each day.  It is NOT a
per-tick delta.

Evidence: ``adapters/jvquant_websocket.py`` calls
    ``buffer.add_price(code, time, price, float(getattr(lv1, "amount", 0.0)))``
The field name on the jvQuant object is ``amount`` which maps to the A-share
realtime feed field "成交额(元)" — the cumulative total, not a tick amount.

CONSEQUENCE FOR ``volume`` per minute bar
-----------------------------------------
The buy-point state machine consumes ``bar.volume`` as a *flow* (e.g.
``breakout_volume_ratio = bar.volume / baseline_volume``).  If we stored the
raw cumulative level, every bar's "volume" would be enormous and comparison
would be meaningless.

Correct per-minute flow:
    volume[minute_k] = cumulative_at_end_of_minute_k
                       - cumulative_at_end_of_minute_{k-1}
    clamped to >= 0  (guards against data anomalies or feed reconnects)

FIRST-BAR VOLUME
----------------
The first minute in the window has no prior-minute baseline, so its delta is
undefined.  We set it to **0.0** rather than using its own cumulative value
(which could be tens of millions CNY from the day open) to avoid a spurious
"huge first-bar spike" that would distort the baseline_volume estimate used by
the state machine.  Downstream callers that compute a baseline window (e.g.
``buypoint_replay.py``) already skip the earliest bars — this is safe.

PARAMETER
---------
``turnover_is_cumulative=True``  (default, production)
    Per-minute volume = delta between consecutive minute-end cumulatives.

``turnover_is_cumulative=False``  (testing / alternate data sources)
    Per-minute volume = sum of per-point turnover values within the minute.
    Use this only when each ``turnover_cny`` value is already a per-tick
    increment, not a running total.
"""

from __future__ import annotations

from collections import defaultdict

from aegis_alpha.events import _parse_timestamp
from aegis_alpha.models import MinuteReplayBar

__all__ = ["rolling_points_to_minute_bars"]


def rolling_points_to_minute_bars(
    points: list[tuple[str, float, float]],
    *,
    turnover_is_cumulative: bool = True,
) -> list[MinuteReplayBar]:
    """Aggregate rolling (timestamp, price, turnover_cny) points into per-minute bars.

    Args:
        points: Sequence of ``(timestamp, price, turnover_cny)`` tuples as
            stored in ``SignalWindowBuffer._points``.  Timestamps are ISO-ish
            strings (e.g. ``"2024-03-01T09:31:05+08:00"``).
        turnover_is_cumulative: When ``True`` (default), ``turnover_cny`` is
            the running day total; per-minute volume is computed as a delta.
            When ``False``, each point's ``turnover_cny`` is treated as an
            independent per-tick amount and summed within the minute.

    Returns:
        List of ``MinuteReplayBar`` in chronological order (earliest minute
        first).  Points whose timestamps cannot be parsed are silently skipped.
    """
    if not points:
        return []

    # ------------------------------------------------------------------
    # 1. Parse timestamps and floor to minute.  Skip unparseable rows.
    # ------------------------------------------------------------------
    # minute_key → list of (price, turnover_cny) in arrival order
    bucket_prices: dict[str, list[float]] = defaultdict(list)
    bucket_turnover: dict[str, list[float]] = defaultdict(list)

    for ts_str, price, turnover_cny in points:
        dt = _parse_timestamp(ts_str)
        if dt is None:
            continue
        # Floor to minute as a sortable ISO minute string "YYYY-MM-DDTHH:MM"
        minute_key = dt.strftime("%Y-%m-%dT%H:%M")
        bucket_prices[minute_key].append(price)
        bucket_turnover[minute_key].append(turnover_cny)

    if not bucket_prices:
        return []

    # ------------------------------------------------------------------
    # 2. Build bars in chronological minute order.
    # ------------------------------------------------------------------
    sorted_keys = sorted(bucket_prices.keys())
    bars: list[MinuteReplayBar] = []
    prev_cumulative: float | None = None

    for minute_key in sorted_keys:
        prices = bucket_prices[minute_key]
        turnovers = bucket_turnover[minute_key]

        last_price = prices[-1]
        hh_mm = minute_key[11:16]  # "HH:MM" slice from "YYYY-MM-DDTHH:MM"

        if turnover_is_cumulative:
            current_cumulative = turnovers[-1]  # last reading = minute-end level
            if prev_cumulative is None:
                # First bar: no prior baseline — use 0.0 (see module docstring)
                volume = 0.0
            else:
                volume = max(0.0, current_cumulative - prev_cumulative)
            prev_cumulative = current_cumulative
        else:
            volume = sum(turnovers)

        bars.append(
            MinuteReplayBar(
                time=hh_mm,
                last_price=last_price,
                volume=volume,
            )
        )

    return bars
