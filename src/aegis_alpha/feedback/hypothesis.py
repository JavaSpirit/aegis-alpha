from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


@dataclass(frozen=True)
class HypothesisInputs:
    snapshot: HistoricalCandidateSnapshot
    hypothesis: dict[str, Any]


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison.

    Returns None when the snapshot payload is not valid JSON.
    """
    try:
        payload = json.loads(inputs.snapshot.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    new_payload = dict(payload)
    new_payload.update(inputs.hypothesis)
    payload_diff: dict[str, Any] = {}
    for key, new_value in inputs.hypothesis.items():
        original_value = payload.get(key, None)
        if original_value != new_value:
            payload_diff[key] = {
                "original": original_value,
                "hypothetical": new_value,
            }

    # P6 starter: until a real re-grading hook is wired, the hypothetical grade
    # is left equal to the original grade. The structured diff is the artifact.
    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=inputs.snapshot.grade_at_pick,
        hypothetical_grade=inputs.snapshot.grade_at_pick,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            "starter: re-grading hook not yet wired; only payload diff returned"
        ],
    )
