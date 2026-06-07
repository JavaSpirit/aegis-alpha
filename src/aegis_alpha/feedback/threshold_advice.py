from __future__ import annotations

from collections import Counter

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    BacktestRun,
    OutcomeAttribution,
    ThresholdAdviceReport,
    ThresholdProposal,
)


_DELTA_MIN = 0.02


def _rule_change_to_proposal(
    *,
    run: BacktestRun,
    key: str,
    value: object,
    delta: float,
) -> ThresholdProposal | None:
    # Grade-remap proposal mappers (promote_b_to_a, downgrade_c_to_reject, flip_a_to_b)
    # removed: program grading is gone; backtest grade-remap re-homed to Phase 7.
    return None


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
