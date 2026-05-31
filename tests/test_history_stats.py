from __future__ import annotations

from pathlib import Path

from aegis_alpha.feedback.history_stats import compute_history_stats
from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_compute_history_stats_with_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day, sealed, gap_up, premium in [
        ("2026-05-25", True, True, 3.0),
        ("2026-05-26", True, False, -1.0),
        ("2026-05-27", False, False, 0.0),
        ("2026-05-28", True, True, 4.0),
    ]:
        store.save_review_outcome(
            CandidateOutcomeReview(
                symbol="002230.SZ",
                trading_day=day,
                touched_limit_up=sealed,
                sealed_second_board=sealed,
                next_day_open_pct=gap_up_pct(gap_up, premium),
                next_day_high_pct=premium,
            )
        )

    stats = compute_history_stats(
        store=store,
        symbol="002230.SZ",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.symbol == "002230.SZ"
    assert stats.sample_size == 4
    # 3/4 sealed
    assert abs(stats.touch_limit_up_success_rate - 0.75) < 1e-6
    # 2/3 of sealed had gap-up (positive next_day_open_pct)
    assert abs(stats.sealed_next_day_gap_up_rate - (2 / 3)) < 1e-6
    # avg of next_day_high_pct: (3 + -1 + 0 + 4) / 4 = 1.5
    assert abs(stats.avg_next_day_premium_pct - 1.5) < 1e-6
    assert stats.confidence in {"medium", "high"}


def test_compute_history_stats_insufficient_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="X",
            trading_day="2026-05-31",
            sealed_second_board=True,
            next_day_open_pct=2.0,
            next_day_high_pct=3.0,
        )
    )

    stats = compute_history_stats(
        store=store,
        symbol="X",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.sample_size == 1
    assert stats.confidence == "insufficient_sample"


def test_compute_history_stats_no_records_returns_zero_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)

    stats = compute_history_stats(
        store=store,
        symbol="UNKNOWN",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.sample_size == 0
    assert stats.confidence == "insufficient_sample"
    assert stats.touch_limit_up_success_rate == 0.0


def gap_up_pct(gap_up: bool, premium: float) -> float:
    """Helper: positive next_day_open_pct only when gap_up is True."""
    return 1.5 if gap_up else -0.5
