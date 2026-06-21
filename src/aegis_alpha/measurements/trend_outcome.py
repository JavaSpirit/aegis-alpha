from __future__ import annotations

from typing import Any

from aegis_alpha.models import MinuteReplayBar, MinuteReplaySnapshot


def summarize_trend_window_outcome(
    snapshot: MinuteReplaySnapshot,
    *,
    window_start: str = "09:31",
    window_end: str = "10:00",
) -> dict[str, Any]:
    """Summarize broad trend-strategy outcome facts from target-day minute bars.

    This is not a second-board label and does not infer trade direction. It only
    describes what happened in the requested replay window relative to previous
    close.
    """
    bars = _windowed_bars(snapshot.bars, window_start=window_start, window_end=window_end)
    previous_close = float(snapshot.previous_close or 0.0)
    if previous_close <= 0:
        return _unavailable(snapshot, window_start, window_end, "missing_previous_close")
    if not bars:
        return _unavailable(snapshot, window_start, window_end, "missing_window_bars")

    open_bar = bars[0]
    high_bar = max(bars, key=lambda item: item.last_price)
    low_bar = min(bars, key=lambda item: item.last_price)
    end_bar = bars[-1]
    future_after_high = [bar for bar in bars if bar.time >= high_bar.time]
    low_after_high = min(future_after_high, key=lambda item: item.last_price) if future_after_high else high_bar

    opening_pct = _pct(open_bar.last_price, previous_close)
    max_gain_pct = _pct(high_bar.last_price, previous_close)
    low_pct = _pct(low_bar.last_price, previous_close)
    window_end_pct = _pct(end_bar.last_price, previous_close)
    drawdown_after_high_pct = _pct(low_after_high.last_price, high_bar.last_price)

    return {
        "symbol": snapshot.symbol,
        "trading_day": snapshot.trading_day,
        "provider": snapshot.provider,
        "data_mode": "trend_window_outcome",
        "window": {"start": window_start, "end": window_end},
        "previous_close": previous_close,
        "window_open_time": open_bar.time,
        "window_open_price": open_bar.last_price,
        "window_open_pct": opening_pct,
        "max_gain_time": high_bar.time,
        "max_gain_price": high_bar.last_price,
        "max_gain_pct": max_gain_pct,
        "window_low_time": low_bar.time,
        "window_low_price": low_bar.last_price,
        "window_low_pct": low_pct,
        "window_end_time": end_bar.time,
        "window_end_price": end_bar.last_price,
        "window_end_pct": window_end_pct,
        "drawdown_after_high_pct": drawdown_after_high_pct,
        "gap_and_fade": opening_pct >= 3.0 and drawdown_after_high_pct <= -2.0 and window_end_pct < opening_pct,
        "morning_followthrough": max_gain_pct >= 3.0 and window_end_pct >= 2.0 and drawdown_after_high_pct > -3.0,
        "weak_no_followthrough": max_gain_pct < 2.0 and window_end_pct <= 0.0,
        "outcome_label": _label(
            opening_pct=opening_pct,
            max_gain_pct=max_gain_pct,
            window_end_pct=window_end_pct,
            drawdown_after_high_pct=drawdown_after_high_pct,
        ),
        "notes": [
            "Trend outcome uses target-day minute bars relative to previous close.",
            "It is a broad strategy outcome label, not a second-board-only label and not a trade instruction.",
            "No exchange-verified active buy/sell direction is inferred.",
        ],
    }


def _windowed_bars(
    bars: list[MinuteReplayBar],
    *,
    window_start: str,
    window_end: str,
) -> list[MinuteReplayBar]:
    return [
        bar
        for bar in bars
        if (not window_start or bar.time >= window_start) and (not window_end or bar.time <= window_end)
    ]


def _unavailable(
    snapshot: MinuteReplaySnapshot,
    window_start: str,
    window_end: str,
    error: str,
) -> dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "trading_day": snapshot.trading_day,
        "provider": snapshot.provider,
        "data_mode": "unavailable",
        "window": {"start": window_start, "end": window_end},
        "error": error,
        "notes": ["Trend outcome unavailable because required minute replay facts are missing."],
    }


def _label(
    *,
    opening_pct: float,
    max_gain_pct: float,
    window_end_pct: float,
    drawdown_after_high_pct: float,
) -> str:
    if opening_pct >= 3.0 and drawdown_after_high_pct <= -2.0 and window_end_pct < opening_pct:
        return "gap_and_fade"
    if max_gain_pct >= 3.0 and window_end_pct >= 2.0 and drawdown_after_high_pct > -3.0:
        return "morning_followthrough"
    if max_gain_pct >= 3.0 and window_end_pct < 1.0:
        return "failed_intraday_breakout"
    if max_gain_pct < 2.0 and window_end_pct <= 0.0:
        return "weak_no_followthrough"
    return "mixed"


def _pct(price: float, base: float) -> float:
    return round((float(price or 0.0) - base) / base * 100.0, 4) if base > 0 else 0.0
