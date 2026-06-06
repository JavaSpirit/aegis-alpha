from __future__ import annotations

from pathlib import Path

import pytest

from aegis_alpha.feedback.backtest import (
    BacktestInputs,
    run_backtest_and_advise,
)
from aegis_alpha.models import (
    CandidateOutcomeReview,
    HistoricalCandidateSnapshot,
    OutcomeAttribution,
)
from aegis_alpha.storage import AegisAlphaStore


@pytest.mark.skip(reason="grade-remap backtest re-homed to Phase 7")
def test_run_backtest_persists_run_and_returns_advice(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    for day, symbol, grade, sealed in [
        ("2026-05-25", "X", "B", True),
        ("2026-05-26", "Y", "B", True),
        ("2026-05-27", "Z", "B", False),
    ]:
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol=symbol,
                trading_day=day,
                grade_at_pick=grade,
                payload_json="{}",
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
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="x",
            symbol="Z",
            trading_day="2026-05-27",
            primary_tag="leader_break_down",
            created_at="2026-05-27T16:00:00+08:00",
        )
    )

    run, advice = run_backtest_and_advise(
        BacktestInputs(
            store=store,
            rule_changes={"promote_b_to_a": True},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.sample_size == 3
    fetched = store.get_backtest_run(run.run_id)
    assert fetched is not None
    assert advice.backtest_run_id == run.run_id
