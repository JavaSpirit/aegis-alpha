"""Pure agent-judgment scorecard: Brier score, calibration, grade hit-rate.

Ground-truth home re-homed from feedback/backtest.py per Phase 7.

No I/O, no store, no network, no adapter. Inputs are already-fetched lists.
Outputs calibration metrics for the AGENT's past judgments vs realized truth.
This is NOT a program re-grade and NOT an order/advice generator.
"""
from __future__ import annotations

from aegis_alpha.models import (
    AgentJudgmentRow,
    AgentJudgmentScorecard,
    AgentReview,
    CandidateOutcomeReview,
)

__all__ = [
    "LIKELIHOOD_PROBABILITY",
    "extract_predictions",
    "build_judgment_rows",
    "compute_scorecard",
]

# Fixed probability mapping for Brier score computation.
# Reflects the agent's implicit probability for each bucket.
LIKELIHOOD_PROBABILITY: dict[str, float] = {
    "high": 0.8,
    "medium": 0.5,
    "low": 0.2,
}


def _trading_day_from_review(review: AgentReview) -> str:
    """Return the YYYY-MM-DD date to use as trading_day for a review's predictions.

    Prefer review.target_time (the intended trading session) over review.created_at
    (when stored). target_time represents the market day the agent was predicting for;
    created_at may be the night before or an admin timestamp. When target_time is absent,
    fall back to created_at date.
    """
    # target_time is the intended trading session — use it when present
    if review.target_time:
        return review.target_time[:10]
    # Fallback: use the creation date
    if review.created_at:
        return review.created_at[:10]
    return ""


def extract_predictions(
    reviews: list[AgentReview],
) -> list[tuple[str, str, str | None, str | None]]:
    """Return (symbol, trading_day, predicted_grade, predicted_likelihood) per prediction.

    Walk payload['per_symbol'] when present (one prediction per item, keyed by
    item['symbol']). Fall back to a single prediction from payload.get('grade') /
    payload.get('promotion_likelihood') paired with review.symbols[0] when exactly
    one symbol is in the review. Skip items with neither grade nor likelihood.

    trading_day source: prefer review.target_time date portion if present, else
    review.created_at date portion (see _trading_day_from_review for rationale).
    """
    results: list[tuple[str, str, str | None, str | None]] = []

    for review in reviews:
        trading_day = _trading_day_from_review(review)
        payload = review.payload or {}
        per_symbol = payload.get("per_symbol")

        if isinstance(per_symbol, list):
            # Walk per_symbol items — one prediction per item
            for item in per_symbol:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "")
                if not symbol:
                    continue
                grade: str | None = item.get("grade") or None
                likelihood: str | None = item.get("promotion_likelihood") or None
                # Skip items with neither grade nor likelihood
                if grade is None and likelihood is None:
                    continue
                results.append((symbol, trading_day, grade, likelihood))
        else:
            # No per_symbol — fall back to single top-level prediction
            # Only emit if review has exactly one symbol (otherwise ambiguous)
            if len(review.symbols) != 1:
                continue
            symbol = review.symbols[0]
            grade = payload.get("grade") or None
            likelihood = payload.get("promotion_likelihood") or None
            # Skip if neither present
            if grade is None and likelihood is None:
                continue
            results.append((symbol, trading_day, grade, likelihood))

    return results


def build_judgment_rows(
    reviews: list[AgentReview],
    outcomes: list[CandidateOutcomeReview],
) -> list[AgentJudgmentRow]:
    """Join each prediction to its realized outcome by (symbol, trading_day).

    A row is produced for every prediction; realized fields are None when no
    matching outcome exists. Outcomes with no matching prediction are ignored.
    Does not mutate input lists or objects.
    """
    # Build lookup: (symbol, trading_day) → outcome
    outcome_lookup: dict[tuple[str, str], CandidateOutcomeReview] = {
        (o.symbol, o.trading_day): o
        for o in outcomes
    }

    rows: list[AgentJudgmentRow] = []
    for sym, day, grade, likelihood in extract_predictions(reviews):
        outcome = outcome_lookup.get((sym, day))
        rows.append(
            AgentJudgmentRow(
                symbol=sym,
                trading_day=day,
                predicted_grade=grade,  # type: ignore[arg-type]
                predicted_likelihood=likelihood,  # type: ignore[arg-type]
                sealed_second_board=outcome.sealed_second_board if outcome else None,
                next_day_open_pct=outcome.next_day_open_pct if outcome else None,
                next_day_high_pct=outcome.next_day_high_pct if outcome else None,
            )
        )

    return rows


def compute_scorecard(
    reviews: list[AgentReview],
    outcomes: list[CandidateOutcomeReview],
    *,
    start_day: str,
    end_day: str,
) -> AgentJudgmentScorecard:
    """Full pipeline: extract predictions → join outcomes → compute calibration metrics.

    sample_size = rows where predicted_likelihood is not None AND
                  sealed_second_board is not None (i.e. scoreable).

    brier_score = mean( (LIKELIHOOD_PROBABILITY[likelihood] - actual)^2 )
        over scoreable rows, where actual = 1.0 if sealed_second_board else 0.0.
        None if sample_size == 0.

    likelihood_calibration[bucket] = {
        'predicted_rate': LIKELIHOOD_PROBABILITY[bucket],
        'realized_seal_rate': mean actual for that bucket,
        'n': count
    } for buckets with n > 0.

    grade_hit_rate[grade] = {
        'realized_seal_rate': mean actual for rows with that grade AND a known
            sealed outcome,
        'n': count
    } for grades with n > 0.

    All rows (even unscoreable) are included in scorecard.rows for transparency.
    No division by zero anywhere.
    """
    all_rows = build_judgment_rows(reviews, outcomes)

    # Scoreable rows: must have BOTH predicted_likelihood and sealed_second_board
    scoreable = [
        r for r in all_rows
        if r.predicted_likelihood is not None and r.sealed_second_board is not None
    ]
    sample_size = len(scoreable)

    # Brier score — None when no scoreable rows
    brier_score: float | None = None
    if sample_size > 0:
        total_sq_err = sum(
            (LIKELIHOOD_PROBABILITY[r.predicted_likelihood] - (1.0 if r.sealed_second_board else 0.0)) ** 2  # type: ignore[index]
            for r in scoreable
        )
        brier_score = total_sq_err / sample_size

    # Calibration buckets: group scoreable rows by predicted_likelihood
    # bucket_accum[likelihood] = list of actuals (0.0 or 1.0)
    bucket_accum: dict[str, list[float]] = {}
    for r in scoreable:
        bucket = r.predicted_likelihood  # guaranteed non-None for scoreable rows
        actual = 1.0 if r.sealed_second_board else 0.0
        if bucket not in bucket_accum:
            bucket_accum[bucket] = []
        bucket_accum[bucket].append(actual)

    likelihood_calibration: dict[str, dict[str, float]] = {}
    for bucket, actuals in bucket_accum.items():
        n = len(actuals)
        if n > 0:  # always true here but guard explicitly
            likelihood_calibration[bucket] = {
                "predicted_rate": LIKELIHOOD_PROBABILITY[bucket],
                "realized_seal_rate": sum(actuals) / n,
                "n": float(n),
            }

    # Grade hit-rate: rows with a known grade AND sealed_second_board is not None
    grade_accum: dict[str, list[float]] = {}
    for r in all_rows:
        if r.predicted_grade is None or r.sealed_second_board is None:
            continue
        grade = r.predicted_grade
        actual = 1.0 if r.sealed_second_board else 0.0
        if grade not in grade_accum:
            grade_accum[grade] = []
        grade_accum[grade].append(actual)

    grade_hit_rate: dict[str, dict[str, float]] = {}
    for grade, actuals in grade_accum.items():
        n = len(actuals)
        if n > 0:
            grade_hit_rate[grade] = {
                "realized_seal_rate": sum(actuals) / n,
                "n": float(n),
            }

    return AgentJudgmentScorecard(
        start_day=start_day,
        end_day=end_day,
        sample_size=sample_size,
        brier_score=brier_score,
        likelihood_calibration=likelihood_calibration,
        grade_hit_rate=grade_hit_rate,
        rows=all_rows,
    )
