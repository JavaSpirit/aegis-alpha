from __future__ import annotations

from aegis_alpha.clock import now_iso
from aegis_alpha.models import DailyReview, DailyReviewItem
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


def generate_daily_review(
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    *,
    trading_day: str,
) -> DailyReview:
    candidates = adapter.get_second_board_candidates()
    items: list[DailyReviewItem] = []
    sealed_count = 0
    for candidate in candidates:
        outcome = store.get_review_outcome(candidate.symbol, trading_day)
        # get_review_outcome returns a placeholder (not None) when no record exists.
        # Detect the placeholder by checking touched_limit_up is not None.
        if outcome and outcome.touched_limit_up is not None:
            sealed = outcome.sealed_second_board
        else:
            sealed = None
        if sealed:
            sealed_count += 1
        touched_limit_up = outcome.touched_limit_up if (outcome and outcome.touched_limit_up is not None) else None
        next_day_open_pct = outcome.next_day_open_pct if (outcome and outcome.touched_limit_up is not None) else None
        items.append(
            DailyReviewItem(
                symbol=candidate.symbol,
                theme=candidate.theme,
                theme_role=candidate.theme_role,
                previous_consecutive_boards=candidate.previous_consecutive_boards,
                touched_limit_up=touched_limit_up,
                sealed_second_board=sealed,
                next_day_open_pct=next_day_open_pct,
            )
        )
    return DailyReview(
        trading_day=trading_day,
        generated_at=now_iso(),
        candidate_count=len(items),
        grade_distribution={},
        sealed_count=sealed_count,
        items=items,
        notes=[
            "Daily review aggregates today's candidate pool and stored outcomes.",
            "Outcomes that have not been recorded show null for touched_limit_up / sealed_second_board.",
        ],
    )
