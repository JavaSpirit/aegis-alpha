from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_list_review_outcomes_filters_by_symbol_and_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for symbol, day, sealed in [
        ("A", "2026-05-25", True),
        ("A", "2026-05-26", False),
        ("A", "2026-05-30", True),
        ("B", "2026-05-26", True),
    ]:
        store.save_review_outcome(
            CandidateOutcomeReview(symbol=symbol, trading_day=day, sealed_second_board=sealed)
        )

    rows = store.list_review_outcomes(symbol="A", start_day="2026-05-25", end_day="2026-05-27")

    assert {row.trading_day for row in rows} == {"2026-05-25", "2026-05-26"}


def test_list_review_outcomes_no_symbol_filter_returns_all(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25", sealed_second_board=True))
    store.save_review_outcome(CandidateOutcomeReview(symbol="B", trading_day="2026-05-25", sealed_second_board=False))

    rows = store.list_review_outcomes(start_day="2026-05-25", end_day="2026-05-25")

    assert {row.symbol for row in rows} == {"A", "B"}


def test_list_review_outcomes_empty_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25"))

    rows = store.list_review_outcomes(start_day="2026-06-01", end_day="2026-06-30")

    assert rows == []
