from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


_GRADE_LADDER = ("REJECT", "C", "B", "A")
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
    orig_seal = _safe_float(original_payload, "seal_amount_cny")
    new_seal = _safe_float(new_payload, "seal_amount_cny")
    if orig_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= new_seal:
        delta += 1
    elif new_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= orig_seal:
        delta -= 1
    orig_speed = _safe_float(original_payload, "five_min_speed_pct")
    new_speed = _safe_float(new_payload, "five_min_speed_pct")
    if orig_speed < _SPEED_BOOST_THRESHOLD <= new_speed:
        delta += 1
    elif new_speed < _SPEED_BOOST_THRESHOLD <= orig_speed:
        delta -= 1
    return delta


def _safe_float(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison against the historical grade.

    Returns None when the snapshot has no historical program grade or when the
    payload is not valid JSON. New candidate flows intentionally do not compute
    program grades; this helper only supports legacy grade-at-pick snapshots.
    """
    if inputs.snapshot.grade_at_pick is None:
        return None  # No program grade to re-grade against; agent grade set in a later phase.
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

    original_grade = inputs.snapshot.grade_at_pick
    grade_delta = _grade_delta_from_crossing(
        original_payload=payload,
        new_payload=new_payload,
    )
    hypothetical_grade = _bump_grade(original_grade, grade_delta)

    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=original_grade,
        hypothetical_grade=hypothetical_grade,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            (
                "Legacy grade sensitivity only; current candidate pipeline exposes "
                "facts for agent-side analysis instead of computing program grades."
            ),
        ],
    )
