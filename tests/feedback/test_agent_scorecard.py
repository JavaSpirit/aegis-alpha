"""TDD tests for src/aegis_alpha/feedback/agent_scorecard.py.

Pure function tests — no I/O, no DB, no network.
"""
from __future__ import annotations

import pytest

from aegis_alpha.models import (
    AgentJudgmentRow,
    AgentJudgmentScorecard,
    AgentReview,
    CandidateOutcomeReview,
)
from aegis_alpha.feedback.agent_scorecard import (
    LIKELIHOOD_PROBABILITY,
    build_judgment_rows,
    compute_scorecard,
    extract_predictions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review(
    *,
    symbols: list[str] | None = None,
    payload: dict | None = None,
    target_time: str = "2026-06-01T09:30:00",
    created_at: str = "2026-06-01T08:00:00",
) -> AgentReview:
    return AgentReview(
        run_type="daily",
        symbols=symbols or [],
        payload=payload or {},
        target_time=target_time,
        created_at=created_at,
    )


def _outcome(
    symbol: str,
    trading_day: str,
    *,
    sealed: bool | None = None,
    next_day_open_pct: float | None = None,
    next_day_high_pct: float | None = None,
) -> CandidateOutcomeReview:
    return CandidateOutcomeReview(
        symbol=symbol,
        trading_day=trading_day,
        sealed_second_board=sealed,
        next_day_open_pct=next_day_open_pct,
        next_day_high_pct=next_day_high_pct,
    )


# ---------------------------------------------------------------------------
# LIKELIHOOD_PROBABILITY constant
# ---------------------------------------------------------------------------

def test_likelihood_probability_values() -> None:
    assert LIKELIHOOD_PROBABILITY["high"] == 0.8
    assert LIKELIHOOD_PROBABILITY["medium"] == 0.5
    assert LIKELIHOOD_PROBABILITY["low"] == 0.2


# ---------------------------------------------------------------------------
# extract_predictions — per_symbol multi-item
# ---------------------------------------------------------------------------

def test_extract_per_symbol_multi() -> None:
    """Walk per_symbol list: one prediction per item with right symbol/grade/likelihood."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
            {"symbol": "300750", "grade": "B", "promotion_likelihood": "medium"},
            {"symbol": "002415", "grade": "C", "promotion_likelihood": "low"},
        ]
    }
    reviews = [_review(symbols=["000001", "300750", "002415"], payload=payload)]
    preds = extract_predictions(reviews)

    assert len(preds) == 3
    symbols = [p[0] for p in preds]
    assert "000001" in symbols
    assert "300750" in symbols
    assert "002415" in symbols

    by_sym = {p[0]: p for p in preds}
    assert by_sym["000001"][2] == "A"      # grade
    assert by_sym["000001"][3] == "high"   # likelihood
    assert by_sym["300750"][2] == "B"
    assert by_sym["300750"][3] == "medium"
    assert by_sym["002415"][2] == "C"
    assert by_sym["002415"][3] == "low"


def test_extract_per_symbol_uses_target_time_date() -> None:
    """trading_day should be the date portion of target_time, not created_at."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
        ]
    }
    reviews = [
        _review(
            symbols=["000001"],
            payload=payload,
            target_time="2026-06-05T09:30:00",
            created_at="2026-06-04T22:00:00",  # different date — created evening before
        )
    ]
    preds = extract_predictions(reviews)
    assert len(preds) == 1
    assert preds[0][1] == "2026-06-05"  # target_time date, not created_at date


def test_extract_falls_back_to_created_at_when_target_time_empty() -> None:
    """When target_time is empty, fall back to created_at date."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
        ]
    }
    reviews = [
        _review(
            symbols=["000001"],
            payload=payload,
            target_time="",
            created_at="2026-06-03T08:00:00",
        )
    ]
    preds = extract_predictions(reviews)
    assert len(preds) == 1
    assert preds[0][1] == "2026-06-03"


# ---------------------------------------------------------------------------
# extract_predictions — single top-level grade + single symbol
# ---------------------------------------------------------------------------

def test_extract_single_top_level_grade() -> None:
    """Single top-level grade + single symbol → 1 prediction."""
    payload = {"grade": "A", "promotion_likelihood": "high"}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    preds = extract_predictions(reviews)

    assert len(preds) == 1
    sym, day, grade, likelihood = preds[0]
    assert sym == "000001"
    assert day == "2026-06-01"
    assert grade == "A"
    assert likelihood == "high"


def test_extract_single_symbol_no_per_symbol() -> None:
    """Top-level grade only, no per_symbol present."""
    payload = {"grade": "B", "promotion_likelihood": "medium"}
    reviews = [_review(symbols=["300750"], payload=payload)]
    preds = extract_predictions(reviews)
    assert len(preds) == 1
    assert preds[0][0] == "300750"
    assert preds[0][2] == "B"


def test_extract_skips_items_without_grade_or_likelihood() -> None:
    """Items with NEITHER grade NOR likelihood are skipped."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
            {"symbol": "300750"},  # no grade, no likelihood → skip
            {"symbol": "002415", "grade": "C"},  # has grade → keep
        ]
    }
    reviews = [_review(symbols=["000001", "300750", "002415"], payload=payload)]
    preds = extract_predictions(reviews)

    symbols = [p[0] for p in preds]
    assert "000001" in symbols
    assert "300750" not in symbols   # skipped
    assert "002415" in symbols


def test_extract_keeps_item_with_only_grade() -> None:
    """Item with grade but no likelihood is kept (grade is sufficient)."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A"},  # no likelihood, but has grade
        ]
    }
    reviews = [_review(symbols=["000001"], payload=payload)]
    preds = extract_predictions(reviews)
    assert len(preds) == 1
    assert preds[0][2] == "A"
    assert preds[0][3] is None


def test_extract_keeps_item_with_only_likelihood() -> None:
    """Item with likelihood but no grade is kept (likelihood is sufficient)."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "promotion_likelihood": "medium"},  # no grade
        ]
    }
    reviews = [_review(symbols=["000001"], payload=payload)]
    preds = extract_predictions(reviews)
    assert len(preds) == 1
    assert preds[0][2] is None
    assert preds[0][3] == "medium"


def test_extract_empty_reviews() -> None:
    """Empty review list returns empty predictions."""
    assert extract_predictions([]) == []


def test_extract_does_not_use_single_symbol_fallback_for_multi_symbol_review() -> None:
    """If no per_symbol but multiple symbols, no prediction emitted (ambiguous)."""
    payload = {"grade": "A", "promotion_likelihood": "high"}
    # 2 symbols and no per_symbol → ambiguous, should not produce a prediction
    reviews = [_review(symbols=["000001", "300750"], payload=payload)]
    preds = extract_predictions(reviews)
    assert len(preds) == 0


# ---------------------------------------------------------------------------
# build_judgment_rows — join
# ---------------------------------------------------------------------------

def test_build_rows_prediction_with_matching_outcome() -> None:
    """Prediction with matching outcome gets realized fields."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
        ]
    }
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=True, next_day_open_pct=9.5, next_day_high_pct=10.0)]

    rows = build_judgment_rows(reviews, outcomes)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "000001"
    assert row.trading_day == "2026-06-01"
    assert row.predicted_grade == "A"
    assert row.predicted_likelihood == "high"
    assert row.sealed_second_board is True
    assert row.next_day_open_pct == pytest.approx(9.5)
    assert row.next_day_high_pct == pytest.approx(10.0)


def test_build_rows_prediction_without_matching_outcome() -> None:
    """Prediction with no matching outcome gets None realized fields."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
        ]
    }
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes: list[CandidateOutcomeReview] = []  # no outcomes

    rows = build_judgment_rows(reviews, outcomes)
    assert len(rows) == 1
    row = rows[0]
    assert row.sealed_second_board is None
    assert row.next_day_open_pct is None
    assert row.next_day_high_pct is None


def test_build_rows_outcome_with_no_matching_prediction_is_ignored() -> None:
    """Outcome with no matching prediction produces no row."""
    reviews: list[AgentReview] = []
    outcomes = [_outcome("000001", "2026-06-01", sealed=True)]

    rows = build_judgment_rows(reviews, outcomes)
    assert rows == []


def test_build_rows_keyed_by_symbol_and_trading_day() -> None:
    """Join uses (symbol, trading_day) as composite key."""
    payload_a = {
        "per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]
    }
    payload_b = {
        "per_symbol": [{"symbol": "000001", "grade": "B", "promotion_likelihood": "low"}]
    }
    reviews = [
        _review(symbols=["000001"], payload=payload_a, target_time="2026-06-01T09:30:00"),
        _review(symbols=["000001"], payload=payload_b, target_time="2026-06-02T09:30:00"),
    ]
    outcomes = [
        _outcome("000001", "2026-06-01", sealed=True),
        _outcome("000001", "2026-06-02", sealed=False),
    ]

    rows = build_judgment_rows(reviews, outcomes)
    assert len(rows) == 2
    by_day = {r.trading_day: r for r in rows}
    assert by_day["2026-06-01"].sealed_second_board is True
    assert by_day["2026-06-01"].predicted_grade == "A"
    assert by_day["2026-06-02"].sealed_second_board is False
    assert by_day["2026-06-02"].predicted_grade == "B"


# ---------------------------------------------------------------------------
# compute_scorecard — Brier math (exact numbers)
# ---------------------------------------------------------------------------

def test_brier_one_high_sealed() -> None:
    """high(0.8) that sealed (1.0) → squared error (0.8-1.0)^2 = 0.04."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=True)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 1
    assert abs(sc.brier_score - 0.04) < 1e-9


def test_brier_one_low_not_sealed() -> None:
    """low(0.2) that did NOT seal (0.0) → squared error (0.2-0.0)^2 = 0.04."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "C", "promotion_likelihood": "low"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=False)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 1
    assert abs(sc.brier_score - 0.04) < 1e-9


def test_brier_two_rows_mean_0_04() -> None:
    """One high-sealed (0.04) + one low-not-sealed (0.04) → mean = 0.04."""
    payload_a = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    payload_b = {"per_symbol": [{"symbol": "300750", "grade": "C", "promotion_likelihood": "low"}]}
    reviews = [
        _review(symbols=["000001"], payload=payload_a, target_time="2026-06-01T09:30:00"),
        _review(symbols=["300750"], payload=payload_b, target_time="2026-06-02T09:30:00"),
    ]
    outcomes = [
        _outcome("000001", "2026-06-01", sealed=True),
        _outcome("300750", "2026-06-02", sealed=False),
    ]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-02")
    assert sc.sample_size == 2
    assert abs(sc.brier_score - 0.04) < 1e-9


def test_brier_medium_not_sealed() -> None:
    """medium(0.5) that did NOT seal → (0.5-0.0)^2 = 0.25."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "B", "promotion_likelihood": "medium"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=False)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 1
    assert abs(sc.brier_score - 0.25) < 1e-9


# ---------------------------------------------------------------------------
# compute_scorecard — calibration buckets
# ---------------------------------------------------------------------------

def test_calibration_bucket_high_3_preds_2_sealed() -> None:
    """3 'high' predictions, 2 sealed → high bucket: realized_seal_rate==2/3, n==3."""
    reviews = []
    outcomes = []
    for i, (sym, sealed) in enumerate([("A001", True), ("A002", True), ("A003", False)]):
        day = f"2026-06-{i+1:02d}"
        payload = {"per_symbol": [{"symbol": sym, "grade": "A", "promotion_likelihood": "high"}]}
        reviews.append(_review(symbols=[sym], payload=payload, target_time=f"{day}T09:30:00"))
        outcomes.append(_outcome(sym, day, sealed=sealed))

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-03")
    cal = sc.likelihood_calibration
    assert "high" in cal
    assert cal["high"]["n"] == 3
    assert abs(cal["high"]["predicted_rate"] - 0.8) < 1e-9
    assert abs(cal["high"]["realized_seal_rate"] - 2 / 3) < 1e-9


def test_calibration_buckets_only_present_for_buckets_with_n_gt_0() -> None:
    """Buckets with n==0 are excluded from likelihood_calibration."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=True)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    # Only "high" predictions exist, so "medium" and "low" should not appear
    assert "high" in sc.likelihood_calibration
    assert "medium" not in sc.likelihood_calibration
    assert "low" not in sc.likelihood_calibration


# ---------------------------------------------------------------------------
# compute_scorecard — grade_hit_rate
# ---------------------------------------------------------------------------

def test_grade_hit_rate_two_A_one_sealed() -> None:
    """2 grade-A rows with known outcomes, 1 sealed → A realized_seal_rate==0.5, n==2."""
    reviews = []
    outcomes = []
    for sym, sealed in [("A001", True), ("A002", False)]:
        day = "2026-06-01"
        payload = {"per_symbol": [{"symbol": sym, "grade": "A", "promotion_likelihood": "high"}]}
        reviews.append(_review(symbols=[sym], payload=payload, target_time=f"{day}T09:30:00"))
        outcomes.append(_outcome(sym, day, sealed=sealed))

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    ghr = sc.grade_hit_rate
    assert "A" in ghr
    assert ghr["A"]["n"] == 2
    assert abs(ghr["A"]["realized_seal_rate"] - 0.5) < 1e-9


def test_grade_hit_rate_only_present_for_grades_with_n_gt_0() -> None:
    """Grade buckets with n==0 are not in grade_hit_rate."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=True)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert "A" in sc.grade_hit_rate
    assert "B" not in sc.grade_hit_rate
    assert "C" not in sc.grade_hit_rate
    assert "REJECT" not in sc.grade_hit_rate


# ---------------------------------------------------------------------------
# EDGE: empty inputs
# ---------------------------------------------------------------------------

def test_empty_inputs_no_crash() -> None:
    """Empty reviews + empty outcomes → valid scorecard with zeros/Nones."""
    sc = compute_scorecard([], [], start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 0
    assert sc.brier_score is None
    assert sc.likelihood_calibration == {}
    assert sc.grade_hit_rate == {}
    assert sc.rows == []


def test_empty_inputs_returns_scorecard_type() -> None:
    sc = compute_scorecard([], [], start_day="2026-06-01", end_day="2026-06-30")
    assert isinstance(sc, AgentJudgmentScorecard)
    assert sc.start_day == "2026-06-01"
    assert sc.end_day == "2026-06-30"


# ---------------------------------------------------------------------------
# EDGE: predictions exist but NO outcomes recorded
# ---------------------------------------------------------------------------

def test_predictions_exist_no_outcomes_no_division_by_zero() -> None:
    """Predictions with no outcomes → sample_size 0, brier None, rows present, no crash."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes: list[CandidateOutcomeReview] = []

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 0
    assert sc.brier_score is None
    assert len(sc.rows) == 1  # row is present but unmatched
    assert sc.rows[0].sealed_second_board is None


# ---------------------------------------------------------------------------
# EDGE: likelihood present but sealed_second_board is None (not scoreable)
# ---------------------------------------------------------------------------

def test_likelihood_present_but_outcome_sealed_unknown_not_scoreable() -> None:
    """Row with likelihood but sealed=None is NOT scoreable (excluded from sample_size/brier)
    but still appears in rows for transparency."""
    payload = {
        "per_symbol": [
            {"symbol": "000001", "grade": "A", "promotion_likelihood": "high"},
        ]
    }
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    # Outcome recorded but seal outcome unknown
    outcomes = [_outcome("000001", "2026-06-01", sealed=None, next_day_open_pct=5.0)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 0     # not scoreable
    assert sc.brier_score is None  # no scoreable rows
    assert len(sc.rows) == 1       # still present for transparency
    assert sc.rows[0].sealed_second_board is None


def test_mixed_scoreable_and_unscoreable_rows() -> None:
    """Mix: 1 scoreable (likelihood+sealed known) + 1 unscoreable (sealed unknown).
    sample_size=1, brier computed only from scoreable row."""
    payload_a = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    payload_b = {"per_symbol": [{"symbol": "300750", "grade": "B", "promotion_likelihood": "medium"}]}
    reviews = [
        _review(symbols=["000001"], payload=payload_a, target_time="2026-06-01T09:30:00"),
        _review(symbols=["300750"], payload=payload_b, target_time="2026-06-02T09:30:00"),
    ]
    outcomes = [
        _outcome("000001", "2026-06-01", sealed=True),   # scoreable
        _outcome("300750", "2026-06-02", sealed=None),   # seal unknown → not scoreable
    ]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-02")
    assert sc.sample_size == 1
    assert len(sc.rows) == 2  # both rows present
    # Brier: only from high-sealed = (0.8-1.0)^2 = 0.04
    assert abs(sc.brier_score - 0.04) < 1e-9


# ---------------------------------------------------------------------------
# Scorecard fields and structure
# ---------------------------------------------------------------------------

def test_scorecard_has_disclaimer() -> None:
    """Scorecard must include a non-empty disclaimer (no-advice signal)."""
    sc = compute_scorecard([], [], start_day="2026-06-01", end_day="2026-06-01")
    assert sc.disclaimer
    assert len(sc.disclaimer) > 10


def test_scorecard_rows_all_are_agent_judgment_rows() -> None:
    """All items in scorecard.rows are AgentJudgmentRow instances."""
    payload = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    reviews = [_review(symbols=["000001"], payload=payload, target_time="2026-06-01T09:30:00")]
    outcomes = [_outcome("000001", "2026-06-01", sealed=True)]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    for row in sc.rows:
        assert isinstance(row, AgentJudgmentRow)


def test_multiple_reviews_same_day_different_symbols() -> None:
    """Multiple reviews on same day for different symbols → multiple predictions."""
    payload_a = {"per_symbol": [{"symbol": "000001", "grade": "A", "promotion_likelihood": "high"}]}
    payload_b = {"per_symbol": [{"symbol": "300750", "grade": "B", "promotion_likelihood": "low"}]}
    reviews = [
        _review(symbols=["000001"], payload=payload_a, target_time="2026-06-01T09:30:00"),
        _review(symbols=["300750"], payload=payload_b, target_time="2026-06-01T09:30:00"),
    ]
    outcomes = [
        _outcome("000001", "2026-06-01", sealed=True),
        _outcome("300750", "2026-06-01", sealed=False),
    ]

    sc = compute_scorecard(reviews, outcomes, start_day="2026-06-01", end_day="2026-06-01")
    assert sc.sample_size == 2
    assert len(sc.rows) == 2
    # Brier: high-sealed=(0.8-1.0)^2=0.04, low-not-sealed=(0.2-0.0)^2=0.04 → mean 0.04
    assert abs(sc.brier_score - 0.04) < 1e-9
