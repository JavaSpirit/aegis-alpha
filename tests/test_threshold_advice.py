from __future__ import annotations

from aegis_alpha.feedback.threshold_advice import propose_threshold_changes
from aegis_alpha.models import BacktestCandidateRow, BacktestRun, OutcomeAttribution


def _run(rule_changes: dict, *, sealed_before: float, sealed_after: float, sample: int = 20) -> BacktestRun:
    return BacktestRun(
        run_id="run1",
        rule_changes=rule_changes,
        start_day="2026-05-01",
        end_day="2026-05-31",
        status="completed",
        sample_size=sample,
        sealed_rate_before=sealed_before,
        sealed_rate_after=sealed_after,
        started_at="2026-05-31T16:00:00+08:00",
        completed_at="2026-05-31T16:00:05+08:00",
    )


def test_proposes_change_when_after_rate_higher_and_sample_sufficient() -> None:
    # Grade-remap proposals removed (program grading gone); proposer now always returns empty.
    run = _run({"promote_b_to_a": True}, sealed_before=0.40, sealed_after=0.55, sample=20)

    report = propose_threshold_changes(run=run, attributions=[])

    assert report.proposals == []  # grade-remap mappers removed; Phase 7 will re-add.


def test_no_proposal_when_after_rate_not_better() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.50, sealed_after=0.45, sample=20)

    report = propose_threshold_changes(run=run, attributions=[])

    assert report.proposals == []


def test_low_confidence_when_sample_too_small() -> None:
    # Grade-remap proposals removed; proposer now always returns empty regardless of sample size.
    run = _run({"promote_b_to_a": True}, sealed_before=0.30, sealed_after=0.60, sample=2)

    report = propose_threshold_changes(run=run, attributions=[])

    assert report.proposals == []  # grade-remap mappers removed; Phase 7 will re-add.


def test_attributions_appear_in_notes() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.4, sealed_after=0.55, sample=20)
    attributions = [
        OutcomeAttribution(
            attribution_id="x",
            symbol="A",
            trading_day="2026-05-25",
            primary_tag="leader_break_down",
            created_at="2026-05-25T16:00:00+08:00",
        ),
        OutcomeAttribution(
            attribution_id="y",
            symbol="B",
            trading_day="2026-05-26",
            primary_tag="leader_break_down",
            created_at="2026-05-26T16:00:00+08:00",
        ),
    ]

    report = propose_threshold_changes(run=run, attributions=attributions)

    note_blob = " ".join(report.notes)
    assert "leader_break_down" in note_blob
