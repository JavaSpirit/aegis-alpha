from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aegis_alpha.measurements.buypoint_replay import replay_buypoint
from aegis_alpha.models import BuyPointThresholds, MinuteReplayBar, MinuteReplaySnapshot


SnapshotGetter = Callable[[str, str], MinuteReplaySnapshot]


def run_historical_strategy_replay_from_items(
    *,
    as_of_day: str,
    target_day: str,
    strategy_items: list[dict[str, Any]],
    get_snapshot: SnapshotGetter,
    window_start: str = "",
    window_end: str = "",
) -> dict[str, Any]:
    """Replay the user's intraday trigger pattern over historical minute bars.

    The caller supplies an as-of strategy watchlist and a snapshot getter. This
    function only exposes target-day minute bars up to each replayed bar via the
    existing state machine; it does not inspect target-day outcome labels.
    """
    results: list[dict[str, Any]] = []
    for item in strategy_items:
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        previous_high = float(item.get("previous_high_price") or 0.0)
        if previous_high <= 0:
            results.append(
                _unavailable_result(
                    item,
                    target_day,
                    "missing_previous_high_price",
                    window_start=window_start,
                    window_end=window_end,
                )
            )
            continue

        snapshot = get_snapshot(symbol, target_day)
        replay_bars = _windowed_bars(snapshot.bars, window_start=window_start, window_end=window_end)
        if not replay_bars:
            results.append(
                _unavailable_result(
                    item,
                    target_day,
                    "missing_minute_bars",
                    window_start=window_start,
                    window_end=window_end,
                )
            )
            continue
        replay_snapshot = snapshot.model_copy(
            update={
                "minute_count": len(replay_bars),
                "bars": replay_bars,
            }
        )

        thresholds = BuyPointThresholds()
        signals = replay_buypoint(
            replay_snapshot,
            previous_high=previous_high,
            thresholds=thresholds,
            same_theme_rising_count=int(item.get("same_theme_first_board_count") or 0),
            baseline_window=3,
        )
        pattern_diagnostics = _diagnose_pattern(
            bars=replay_snapshot.bars,
            previous_high=previous_high,
            thresholds=thresholds,
            baseline_window=3,
            signal_count=len(signals),
        )
        first_bar = replay_snapshot.bars[0]
        last_bar = replay_snapshot.bars[-1]
        results.append(
            {
                "symbol": symbol,
                "name": item.get("name", ""),
                "theme": item.get("theme", "unknown"),
                "as_of_day": as_of_day,
                "target_day": target_day,
                "replay_trading_day": replay_snapshot.trading_day,
                "data_mode": replay_snapshot.data_mode,
                "previous_high_price": previous_high,
                "avg_turnover_10d_cny": item.get("avg_turnover_10d_cny", 0.0),
                "avg_turnover_10d_pass": item.get("avg_turnover_10d_pass", False),
                "prev_day_volume_shrink_ratio": item.get("prev_day_volume_shrink_ratio", 0.0),
                "prev_day_shrink": item.get("prev_day_shrink", False),
                "as_of_turnover_cny": item.get("as_of_turnover_cny", 0.0),
                "as_of_high_broke_previous_high": item.get("as_of_high_broke_previous_high", False),
                "theme_continuity_label": (item.get("theme_continuity") or {}).get("continuity_label", "unknown"),
                "theme_continuity": item.get("theme_continuity", {}),
                "same_theme_first_board_count": item.get("same_theme_first_board_count", 0),
                "minute_count_total": snapshot.minute_count,
                "minute_count_replayed": len(replay_snapshot.bars),
                "replay_window": f"{first_bar.time}-{last_bar.time}",
                "requested_window": {
                    "start": window_start,
                    "end": window_end,
                },
                "signal_count": len(signals),
                "signals": [signal.model_dump() for signal in signals],
                "first_triggered_at": signals[0].triggered_at if signals else "",
                "pattern_diagnostics": pattern_diagnostics,
                "data_gaps": [
                    "Historical Level-2 big-order buy ratio is not connected.",
                    "CLS popup/news alignment is not connected.",
                    "Off-platform theme news validation is not connected.",
                ],
                "notes": [
                    "Historical replay uses minute bars and the pure buy-point state machine.",
                    "Signals are research alerts only, not buy/sell/order instructions.",
                    "No target-day outcome label is used in this replay result.",
                ],
            }
        )

    return {
        "as_of_day": as_of_day,
        "target_day": target_day,
        "data_mode": "historical_replay",
        "requested_window": {
            "start": window_start,
            "end": window_end,
        },
        "result_count": len(results),
        "results": results,
        "notes": [
            "Strict replay: observation facts come from as_of_day; intraday trigger facts come from target_day minute bars.",
            "Outcome labels such as sealed_next_day or next_day premium are intentionally absent.",
        ],
        "disclaimer": "Research replay only; not a buy/sell/order instruction.",
    }


def _windowed_bars(
    bars: list[MinuteReplayBar],
    *,
    window_start: str = "",
    window_end: str = "",
) -> list[MinuteReplayBar]:
    if not window_start and not window_end:
        return bars
    return [
        bar
        for bar in bars
        if (not window_start or bar.time >= window_start) and (not window_end or bar.time <= window_end)
    ]


def _diagnose_pattern(
    *,
    bars: list[MinuteReplayBar],
    previous_high: float,
    thresholds: BuyPointThresholds,
    baseline_window: int,
    signal_count: int,
) -> dict[str, Any]:
    baseline_bars = bars[:baseline_window]
    baseline_volume = sum(bar.volume for bar in baseline_bars) / len(baseline_bars) if baseline_bars else 0.0
    evaluated_bars = bars[baseline_window:]
    max_bar = max(bars, key=lambda bar: bar.last_price)
    first_cross = next((bar for bar in bars if bar.last_price > previous_high), None)
    first_evaluated_cross = next((bar for bar in evaluated_bars if bar.last_price > previous_high), None)
    first_confirmed = next(
        (
            bar
            for bar in evaluated_bars
            if bar.last_price > previous_high
            and _volume_ratio(bar.volume, baseline_volume) >= thresholds.breakout_volume_ratio_min
        ),
        None,
    )
    opening_cross = next((bar for bar in baseline_bars if bar.last_price > previous_high), None)

    if signal_count > 0:
        reason = "signal_triggered"
    elif first_cross is None:
        reason = "never_crossed_previous_high"
    elif opening_cross is not None and first_confirmed is None:
        reason = "opening_breakout_candidate_but_no_qualified_pullback_resurge"
    elif first_confirmed is None:
        reason = "crossed_previous_high_but_no_volume_confirmed_breakout"
    else:
        reason = "volume_confirmed_breakout_but_no_qualified_pullback_resurge"

    return {
        "thresholds": {
            "breakout_volume_ratio_min": thresholds.breakout_volume_ratio_min,
            "pullback_volume_shrink_max": thresholds.pullback_volume_shrink_max,
            "resurge_strength_min": thresholds.resurge_strength_min,
            "pullback_max_drawdown_pct": thresholds.pullback_max_drawdown_pct,
            "baseline_window": baseline_window,
        },
        "baseline_volume": round(baseline_volume, 2),
        "max_price": max_bar.last_price,
        "max_price_time": max_bar.time,
        "max_price_above_previous_high_pct": round((max_bar.last_price - previous_high) / previous_high * 100.0, 4)
        if previous_high > 0
        else 0.0,
        "crossed_previous_high": first_cross is not None,
        "first_cross_time": first_cross.time if first_cross else "",
        "first_cross_price": first_cross.last_price if first_cross else 0.0,
        "first_cross_volume_ratio": _volume_ratio(first_cross.volume, baseline_volume) if first_cross else 0.0,
        "opening_window_crossed_previous_high": opening_cross is not None,
        "opening_breakout_candidate": opening_cross is not None,
        "opening_window_cross_time": opening_cross.time if opening_cross else "",
        "first_evaluated_cross_time": first_evaluated_cross.time if first_evaluated_cross else "",
        "first_evaluated_cross_price": first_evaluated_cross.last_price if first_evaluated_cross else 0.0,
        "first_evaluated_cross_volume_ratio": _volume_ratio(first_evaluated_cross.volume, baseline_volume)
        if first_evaluated_cross
        else 0.0,
        "volume_confirmed_breakout": first_confirmed is not None,
        "first_volume_confirmed_breakout_time": first_confirmed.time if first_confirmed else "",
        "first_volume_confirmed_breakout_price": first_confirmed.last_price if first_confirmed else 0.0,
        "first_volume_confirmed_breakout_ratio": _volume_ratio(first_confirmed.volume, baseline_volume)
        if first_confirmed
        else 0.0,
        "no_signal_reason": reason,
    }


def _volume_ratio(volume: float, baseline_volume: float) -> float:
    return round(volume / baseline_volume, 6) if baseline_volume > 0 else 0.0


def post_signal_outcome(
    snapshot: MinuteReplaySnapshot,
    *,
    triggered_at: str,
) -> dict[str, Any]:
    """Summarize post-trigger minute-bar outcome for calibration only."""
    if not triggered_at:
        return {
            "ok": False,
            "error": "missing_triggered_at",
        }
    bars = snapshot.bars
    trigger_bar = next((bar for bar in bars if bar.time == triggered_at), None)
    if trigger_bar is None or trigger_bar.last_price <= 0:
        return {
            "ok": False,
            "error": "missing_trigger_bar",
            "triggered_at": triggered_at,
        }

    future_bars = [bar for bar in bars if bar.time >= triggered_at]
    if not future_bars:
        return {
            "ok": False,
            "error": "missing_future_bars",
            "triggered_at": triggered_at,
        }

    high_bar = max(future_bars, key=lambda bar: bar.last_price)
    low_bar = min(future_bars, key=lambda bar: bar.last_price)
    close_bar = future_bars[-1]
    trigger_price = trigger_bar.last_price
    return {
        "ok": True,
        "triggered_at": triggered_at,
        "trigger_price": round(trigger_price, 4),
        "post_trigger_high_time": high_bar.time,
        "post_trigger_high_price": high_bar.last_price,
        "post_trigger_high_pct": _price_pct(high_bar.last_price, trigger_price),
        "post_trigger_low_time": low_bar.time,
        "post_trigger_low_price": low_bar.last_price,
        "post_trigger_low_pct": _price_pct(low_bar.last_price, trigger_price),
        "close_time": close_bar.time,
        "close_price": close_bar.last_price,
        "close_pct_from_trigger": _price_pct(close_bar.last_price, trigger_price),
        "closed_above_trigger": close_bar.last_price >= trigger_price,
        "notes": [
            "Post-trigger outcome uses bars after the alert and is for historical calibration only.",
            "It is not available to an as-of intraday decision at trigger time.",
        ],
    }


def _price_pct(price: float, base: float) -> float:
    return round((price - base) / base * 100.0, 4) if base > 0 else 0.0


def _unavailable_result(
    item: dict[str, Any],
    target_day: str,
    error: str,
    *,
    window_start: str = "",
    window_end: str = "",
) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol", ""),
        "name": item.get("name", ""),
        "theme": item.get("theme", "unknown"),
        "target_day": target_day,
        "data_mode": "unavailable",
        "error": error,
        "requested_window": {
            "start": window_start,
            "end": window_end,
        },
        "signal_count": 0,
        "signals": [],
        "data_gaps": [error],
        "notes": ["Replay skipped for this symbol because required historical facts are unavailable."],
    }
