from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.reviews.daily import generate_daily_review
from aegis_alpha.storage import AegisAlphaStore


def test_daily_review_aggregates_grades_and_outcomes(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            touched_limit_up=True,
            sealed_second_board=True,
            next_day_open_pct=2.4,
        )
    )
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="300024.SZ",
            trading_day="2026-05-31",
            touched_limit_up=False,
            sealed_second_board=False,
        )
    )
    adapter = MockMarketDataAdapter()

    review = generate_daily_review(adapter, store, trading_day="2026-05-31")

    assert review.trading_day == "2026-05-31"
    assert review.candidate_count == 2
    assert review.grade_distribution
    assert review.sealed_count == 1
    assert {item.symbol for item in review.items} == {"002230.SZ", "300024.SZ"}


def test_daily_review_with_no_outcomes_has_zero_sealed(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    review = generate_daily_review(adapter, store, trading_day="2026-05-31")

    assert review.sealed_count == 0
    for item in review.items:
        assert item.touched_limit_up is None
