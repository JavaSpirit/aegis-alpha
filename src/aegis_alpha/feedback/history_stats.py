from __future__ import annotations

import statistics

from aegis_alpha.models import HistoryStats, HistoryStatsConfidence
from aegis_alpha.storage import AegisAlphaStore


_INSUFFICIENT_SAMPLE_BELOW = 3
_MEDIUM_CONFIDENCE_BELOW = 10


def _confidence_from_sample(size: int) -> HistoryStatsConfidence:
    if size < _INSUFFICIENT_SAMPLE_BELOW:
        return "insufficient_sample"
    if size < _MEDIUM_CONFIDENCE_BELOW:
        return "medium"
    return "high"


def compute_history_stats(
    *,
    store: AegisAlphaStore,
    symbol: str,
    start_day: str,
    end_day: str,
) -> HistoryStats:
    """Compute touch-limit-up success rate, sealed-next-day gap-up rate, and
    next-day premium statistics from review_outcomes within the window.

    A review is counted toward the sample if either touched_limit_up or
    sealed_second_board is non-null. next_day_open_pct > 0 is treated as
    "gap up" for sealed candidates.
    """
    outcomes = store.list_review_outcomes(symbol=symbol, start_day=start_day, end_day=end_day)
    countable = [
        outcome
        for outcome in outcomes
        if outcome.touched_limit_up is not None or outcome.sealed_second_board is not None
    ]
    sample_size = len(countable)

    sealed_outcomes = [outcome for outcome in countable if outcome.sealed_second_board]
    touch_rate = len(sealed_outcomes) / sample_size if sample_size else 0.0

    gap_up_among_sealed = [
        outcome for outcome in sealed_outcomes if (outcome.next_day_open_pct or 0.0) > 0
    ]
    gap_up_rate = len(gap_up_among_sealed) / len(sealed_outcomes) if sealed_outcomes else 0.0

    premiums = [outcome.next_day_high_pct or 0.0 for outcome in countable]
    avg_premium = round(sum(premiums) / sample_size, 4) if sample_size else 0.0
    median_premium = round(statistics.median(premiums), 4) if premiums else 0.0

    # Rates use 6 decimal places (not 4) so common fractions like 2/3 remain
    # within the 1e-6 tolerance downstream comparisons rely on.
    return HistoryStats(
        symbol=symbol,
        sample_size=sample_size,
        sample_window_start=start_day,
        sample_window_end=end_day,
        touch_limit_up_success_rate=round(touch_rate, 6),
        sealed_next_day_gap_up_rate=round(gap_up_rate, 6),
        median_next_day_premium_pct=median_premium,
        avg_next_day_premium_pct=avg_premium,
        confidence=_confidence_from_sample(sample_size),
        notes=[
            f"Window: {start_day} to {end_day}.",
            f"Sample size: {sample_size}.",
        ],
    )
