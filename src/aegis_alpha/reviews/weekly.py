from __future__ import annotations

from collections import defaultdict

from aegis_alpha.clock import now_iso
from aegis_alpha.models import WeeklyPatternReport
from aegis_alpha.storage import AegisAlphaStore


def generate_weekly_pattern_report(
    store: AegisAlphaStore,
    *,
    start_day: str,
    end_day: str,
) -> WeeklyPatternReport:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    samples = 0
    reviews = store.list_agent_reviews_between(start_day, end_day)
    for review in reviews:
        for symbol, grade in zip(review.symbols, review.grades):
            target_day = review.target_time[:10] if review.target_time else ""
            outcome = store.get_review_outcome(symbol, target_day)
            # get_review_outcome returns a placeholder when no record exists.
            # Skip entries where sealed_second_board is not set (placeholder has None).
            sealed = outcome.sealed_second_board
            if sealed is None:
                continue
            label = "sealed" if sealed else "broken"
            matrix[grade][label] += 1
            samples += 1
    return WeeklyPatternReport(
        start_day=start_day,
        end_day=end_day,
        generated_at=now_iso(),
        grade_outcome_matrix={key: dict(value) for key, value in matrix.items()},
        sample_size=samples,
        notes=[
            f"Sampled {samples} grade/outcome pairs from agent_reviews between {start_day} and {end_day}.",
        ],
    )
