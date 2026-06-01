from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


_GRADE_LADDER = ("REJECT", "C", "B", "A")
# CALIBRATE: see config/p6_thresholds.yaml — these starter rules apply only inside
# simulate_outcome and are intentionally simpler than the real candidate_grade.
_SEAL_AMOUNT_BOOST_THRESHOLD = 500_000_000.0
_SPEED_BOOST_THRESHOLD = 5.0


@dataclass(frozen=True)
class HypothesisInputs:
    snapshot: HistoricalCandidateSnapshot
    hypothesis: dict[str, Any]


def _bump_grade(current: str, steps: int) -> str:
    if current not in _GRADE_LADDER:
        return current
    idx = _GRADE_LADDER.index(current)
    new_idx = max(0, min(len(_GRADE_LADDER) - 1, idx + steps))
    return _GRADE_LADDER[new_idx]


def _grade_delta_from_crossing(
    *, original_payload: dict[str, Any], new_payload: dict[str, Any]
) -> int:
    """Return integer steps to move along _GRADE_LADDER given the crossings.

    Each "crossing" of a starter threshold contributes +1 (upward) or -1
    (downward). Multiple fields stack.
    """
    delta = 0
    orig_seal = float(original_payload.get("seal_amount_cny") or 0)
    new_seal = float(new_payload.get("seal_amount_cny") or 0)
    if orig_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= new_seal:
        delta += 1
    elif new_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= orig_seal:
        delta -= 1
    orig_speed = float(original_payload.get("five_min_speed_pct") or 0)
    new_speed = float(new_payload.get("five_min_speed_pct") or 0)
    if orig_speed < _SPEED_BOOST_THRESHOLD <= new_speed:
        delta += 1
    elif new_speed < _SPEED_BOOST_THRESHOLD <= orig_speed:
        delta -= 1
    return delta


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

    delta = _grade_delta_from_crossing(
        original_payload=payload, new_payload=new_payload,
    )
    hypothetical_grade = _bump_grade(inputs.snapshot.grade_at_pick, delta)

    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=inputs.snapshot.grade_at_pick,
        hypothetical_grade=hypothetical_grade,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            f"P7 starter re-grade: delta={delta} on _GRADE_LADDER",
        ],
    )
