from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    BacktestCandidateRow,
    BacktestRun,
    CandidateGrade,
)
from aegis_alpha.storage import AegisAlphaStore


@dataclass(frozen=True)
class BacktestInputs:
    store: AegisAlphaStore
    rule_changes: dict[str, Any]
    start_day: str
    end_day: str


def _run_id(start_day: str, end_day: str, rule_changes: dict[str, Any]) -> str:
    seed = f"{start_day}|{end_day}|{sorted(rule_changes.items())}|{now_iso()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _apply_rule_changes(grade: CandidateGrade, rule_changes: dict[str, Any]) -> CandidateGrade:
    """Apply a small set of supported rule_changes to remap a grade.

    Supported keys:
      - promote_b_to_a: bool — every B becomes A
      - downgrade_c_to_reject: bool — every C becomes REJECT
      - flip_a_to_b: bool — every A becomes B (sanity test)
    """
    if rule_changes.get("promote_b_to_a") and grade == "B":
        return "A"
    if rule_changes.get("downgrade_c_to_reject") and grade == "C":
        return "REJECT"
    if rule_changes.get("flip_a_to_b") and grade == "A":
        return "B"
    return grade


def _sealed_rate(rows: list[BacktestCandidateRow], *, use_new_grade: bool) -> float:
    promoted = [
        row for row in rows
        if (use_new_grade and row.new_grade in {"A", "B"})
        or (not use_new_grade and row.original_grade in {"A", "B"})
    ]
    if not promoted:
        return 0.0
    sealed = [row for row in promoted if row.sealed_second_board]
    return round(len(sealed) / len(promoted), 4)


def backtest_grading_rule(inputs: BacktestInputs) -> BacktestRun:
    """Run a backtest on stored historical snapshots within the window.

    Pure function — does not persist the run. Persistence is handled by
    storage.save_backtest_run in Task 13.
    """
    started_at = now_iso()
    snapshots = inputs.store.list_historical_snapshots_between(
        start_day=inputs.start_day,
        end_day=inputs.end_day,
    )

    rows: list[BacktestCandidateRow] = []
    for snap in snapshots:
        outcome = inputs.store.get_review_outcome(snap.symbol, snap.trading_day)
        sealed = outcome.sealed_second_board if outcome.sealed_second_board is not None else None
        new_grade = _apply_rule_changes(snap.grade_at_pick, inputs.rule_changes)
        rows.append(
            BacktestCandidateRow(
                symbol=snap.symbol,
                trading_day=snap.trading_day,
                original_grade=snap.grade_at_pick,
                new_grade=new_grade,
                sealed_second_board=sealed,
                next_day_open_pct=outcome.next_day_open_pct,
            )
        )

    distribution_before: dict[str, int] = dict(Counter(row.original_grade for row in rows))
    distribution_after: dict[str, int] = dict(Counter(row.new_grade for row in rows))

    completed_at = now_iso()
    return BacktestRun(
        run_id=_run_id(inputs.start_day, inputs.end_day, inputs.rule_changes),
        rule_changes=dict(inputs.rule_changes),
        start_day=inputs.start_day,
        end_day=inputs.end_day,
        status="completed",
        sample_size=len(rows),
        grade_distribution_before=distribution_before,
        grade_distribution_after=distribution_after,
        sealed_rate_before=_sealed_rate(rows, use_new_grade=False),
        sealed_rate_after=_sealed_rate(rows, use_new_grade=True),
        rows=rows,
        started_at=started_at,
        completed_at=completed_at,
        notes=[
            f"Backtest over {len(rows)} historical snapshots from {inputs.start_day} to {inputs.end_day}.",
            f"Rule changes: {sorted(inputs.rule_changes.items())}.",
        ],
    )
