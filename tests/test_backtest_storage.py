from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import BacktestRun
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_backtest_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    run = BacktestRun(
        run_id="run123",
        rule_changes={"promote_b_to_a": True},
        start_day="2026-05-01",
        end_day="2026-05-31",
        status="completed",
        sample_size=10,
        sealed_rate_before=0.4,
        sealed_rate_after=0.55,
        started_at="2026-05-31T16:00:00+08:00",
        completed_at="2026-05-31T16:00:05+08:00",
    )

    store.save_backtest_run(run)
    fetched = store.get_backtest_run("run123")

    assert fetched is not None
    assert fetched.sealed_rate_after == 0.55


def test_list_backtest_runs_by_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for run_id, status in [("a", "completed"), ("b", "running"), ("c", "completed")]:
        store.save_backtest_run(
            BacktestRun(
                run_id=run_id,
                start_day="2026-05-01",
                end_day="2026-05-31",
                status=status,
            )
        )

    completed = store.list_backtest_runs(status="completed")

    assert {row.run_id for row in completed} == {"a", "c"}
