from __future__ import annotations

from pathlib import Path

from aegis_alpha.feedback.backtest import (
    BacktestInputs,
    backtest_grading_rule,
)
from aegis_alpha.models import CandidateOutcomeReview, HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def _seed_three_days(store: AegisAlphaStore) -> None:
    days = [
        ("2026-05-25", "X", "B", True),
        ("2026-05-26", "Y", "C", False),
        ("2026-05-27", "Z", "A", True),
    ]
    for day, symbol, grade, sealed in days:
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol=symbol,
                trading_day=day,
                grade_at_pick=grade,
                payload_json=f'{{"current_change_pct": 9.8, "five_min_speed_pct": 2.0}}',
                created_at=f"{day}T09:30:00+08:00",
            )
        )
        store.save_review_outcome(
            CandidateOutcomeReview(
                symbol=symbol,
                trading_day=day,
                touched_limit_up=sealed,
                sealed_second_board=sealed,
            )
        )


def test_backtest_no_changes_keeps_grades_constant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_three_days(store)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.sample_size == 3
    assert run.status == "completed"
    for row in run.rows:
        assert row.original_grade == row.new_grade


def test_backtest_with_promote_b_to_a_changes_distribution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_three_days(store)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={"promote_b_to_a": True},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.grade_distribution_before.get("B", 0) == 1
    assert run.grade_distribution_after.get("A", 0) == run.grade_distribution_before.get("A", 0) + 1
    assert run.grade_distribution_after.get("B", 0) == 0


def test_backtest_empty_window_is_completed_with_zero_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={},
            start_day="2026-06-01",
            end_day="2026-06-30",
        )
    )

    assert run.status == "completed"
    assert run.sample_size == 0
    assert run.sealed_rate_before == 0.0
    assert run.sealed_rate_after == 0.0
