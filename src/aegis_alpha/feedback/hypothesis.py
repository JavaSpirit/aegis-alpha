from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.adapters.jvquant.scoring import candidate_grade
from aegis_alpha.grading import CandidateGradingConfig
from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


_GRADE_LADDER = ("REJECT", "C", "B", "A")
# CALIBRATE: see config/p6_thresholds.yaml — these starter rules apply only inside
# simulate_outcome and are intentionally simpler than the real candidate_grade.
_SEAL_AMOUNT_BOOST_THRESHOLD = 500_000_000.0
_SPEED_BOOST_THRESHOLD = 5.0
_GRADE_FALLBACK = "C"


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


def _safe_float(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(payload: dict[str, Any], key: str, default: int = 0) -> int:
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _grade_via_candidate_grade(
    payload: dict[str, Any], *, config: CandidateGradingConfig
) -> str:
    """Apply candidate_grade() to payload fields and return the resulting grade."""
    try:
        return candidate_grade(
            action=str(payload.get("action") or "active"),
            change_pct=_safe_float(
                payload,
                "change_pct",
                default=config.candidate.reject_change_pct_below,
            ),
            five_min_speed_pct=_safe_float(payload, "five_min_speed_pct"),
            big_order_net_inflow_ratio=_safe_float(
                payload, "big_order_net_inflow_ratio"
            ),
            orderbook_quality=_safe_float(payload, "orderbook_quality_score"),
            theme_count=_safe_int(payload, "same_theme_rising_count"),
            first_limit_up_time=str(payload.get("first_limit_up_time") or "unknown"),
            seal_amount_cny=_safe_float(payload, "seal_amount_cny"),
            seal_to_turnover_ratio=_safe_float(payload, "seal_to_turnover_ratio"),
            config=config,
        )
    except Exception:
        return _GRADE_FALLBACK


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison with re-graded hypothetical_grade.

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

    config = CandidateGradingConfig()
    original_grade = _grade_via_candidate_grade(payload, config=config)
    hypothetical_grade = _grade_via_candidate_grade(new_payload, config=config)

    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=inputs.snapshot.grade_at_pick or original_grade,
        hypothetical_grade=hypothetical_grade,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            "P8: re-graded via candidate_grade() with hypothesis-overridden payload",
        ],
    )
