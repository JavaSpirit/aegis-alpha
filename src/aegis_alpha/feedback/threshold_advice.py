from __future__ import annotations

import hashlib
from collections import Counter

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    BacktestRun,
    HistoryStatsConfidence,
    OutcomeAttribution,
    ThresholdAdviceReport,
    ThresholdProposal,
)


_LARGE_SAMPLE = 30
_SMALL_SAMPLE = 5
_DELTA_MIN = 0.02


def _confidence(sample: int) -> HistoryStatsConfidence:
    if sample < _SMALL_SAMPLE:
        return "low"
    if sample < _LARGE_SAMPLE:
        return "medium"
    return "high"


def _proposal_id(run_id: str, key: str) -> str:
    seed = f"{run_id}|{key}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _rule_change_to_proposal(
    *,
    run: BacktestRun,
    key: str,
    value: object,
    delta: float,
) -> ThresholdProposal | None:
    if not value:
        return None
    field_path = ""
    rationale = ""
    current_value = 0.0
    suggested_value = 0.0
    if key == "promote_b_to_a":
        field_path = "candidate_grading.candidate.b_change_pct"
        current_value = 7.0
        suggested_value = 8.5
        rationale = (
            "Backtest shows promoting B to A increases sealed-rate; "
            "consider raising the change_pct threshold for B-grade so the bar matches the new ceiling."
        )
    elif key == "downgrade_c_to_reject":
        field_path = "candidate_grading.candidate.reject_change_pct_below"
        current_value = 5.0
        suggested_value = 6.0
        rationale = (
            "Backtest shows downgrading C to REJECT removes losers without dropping sealed-rate; "
            "consider raising the reject_change_pct floor."
        )
    elif key == "flip_a_to_b":
        field_path = "candidate_grading.candidate.a_min_change_pct"
        current_value = 9.5
        suggested_value = 10.0
        rationale = (
            "Backtest shows flipping A to B did not hurt sealed-rate; consider tightening the A-grade floor."
        )
    else:
        return None
    return ThresholdProposal(
        proposal_id=_proposal_id(run.run_id, key),
        field_path=field_path,
        current_value=current_value,
        suggested_value=suggested_value,
        rationale=rationale,
        backtest_run_id=run.run_id,
        sample_size=run.sample_size,
        sealed_rate_delta=round(delta, 4),
        confidence=_confidence(run.sample_size),
        created_at=now_iso(),
    )


def propose_threshold_changes(
    *,
    run: BacktestRun,
    attributions: list[OutcomeAttribution],
) -> ThresholdAdviceReport:
    """Generate threshold proposals from a completed backtest + recent attributions."""
    delta = run.sealed_rate_after - run.sealed_rate_before
    proposals: list[ThresholdProposal] = []

    if delta >= _DELTA_MIN:
        for key, value in run.rule_changes.items():
            proposal = _rule_change_to_proposal(
                run=run,
                key=str(key),
                value=value,
                delta=delta,
            )
            if proposal is not None:
                proposals.append(proposal)

    notes: list[str] = [
        f"Backtest sealed_rate before={run.sealed_rate_before:.4f}, after={run.sealed_rate_after:.4f}, delta={delta:+.4f}.",
        f"Sample size: {run.sample_size}.",
    ]
    if attributions:
        tag_counter = Counter(a.primary_tag for a in attributions)
        top_tags = ", ".join(f"{tag}({count})" for tag, count in tag_counter.most_common(3))
        notes.append(f"Top attribution tags in window: {top_tags}.")

    return ThresholdAdviceReport(
        backtest_run_id=run.run_id,
        generated_at=now_iso(),
        proposals=proposals,
        notes=notes,
    )
