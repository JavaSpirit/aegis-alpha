from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import AgentReview, CandidateOutcomeReview
from aegis_alpha.reviews.weekly import generate_weekly_pattern_report
from aegis_alpha.storage import AegisAlphaStore


def test_weekly_report_builds_grade_outcome_matrix(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    # Persist a few candidate-day outcomes; reuse review_outcomes table.
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25", sealed_second_board=True))
    store.save_review_outcome(CandidateOutcomeReview(symbol="B", trading_day="2026-05-26", sealed_second_board=False))
    store.save_review_outcome(CandidateOutcomeReview(symbol="C", trading_day="2026-05-27", sealed_second_board=True))

    # Weekly is grade × outcome — we need agent_reviews carrying grade.
    review = AgentReview(run_type="historical_eval", target_time="2026-05-25T10:00:00+08:00", symbols=["A"], grades=["A"])
    store.save_agent_review(review)
    review = AgentReview(run_type="historical_eval", target_time="2026-05-26T10:00:00+08:00", symbols=["B"], grades=["B"])
    store.save_agent_review(review)
    review = AgentReview(run_type="historical_eval", target_time="2026-05-27T10:00:00+08:00", symbols=["C"], grades=["A"])
    store.save_agent_review(review)

    report = generate_weekly_pattern_report(store, start_day="2026-05-25", end_day="2026-05-29")

    assert report.sample_size == 3
    assert "A" in report.grade_outcome_matrix
    assert report.grade_outcome_matrix["A"]["sealed"] == 2
    assert report.grade_outcome_matrix["B"]["broken"] == 1
