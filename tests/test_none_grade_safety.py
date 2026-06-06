"""Tests that grade_at_pick=None is handled safely after program grading removal.

These tests were written RED (failing) first, then fixed by:
- hypothesis.py: return None early when grade_at_pick is None
- models.py: SimilarSetupResult.match_grade_at_pick changed to CandidateGrade | None = None
"""
from __future__ import annotations

from aegis_alpha.feedback.hypothesis import HypothesisInputs, simulate_outcome
from aegis_alpha.models import HistoricalCandidateSnapshot, SimilarSetupResult


def _snapshot(grade_at_pick=None, payload_json='{"seal_amount_cny": 100000000}'):
    return HistoricalCandidateSnapshot(
        symbol="000001.SZ",
        trading_day="2026-06-06",
        grade_at_pick=grade_at_pick,
        payload_json=payload_json,
        created_at="2026-06-06T09:30:00+08:00",
    )


def test_simulate_outcome_returns_none_when_grade_at_pick_is_none():
    """Crash 1: simulate_outcome must not raise when grade_at_pick is None."""
    snap = _snapshot(grade_at_pick=None)
    inputs = HypothesisInputs(snapshot=snap, hypothesis={"seal_amount_cny": 600_000_000})

    result = simulate_outcome(inputs)

    assert result is None, (
        "simulate_outcome should return None for grade-less snapshots "
        "(program grade removed; no grade to re-grade against)"
    )


def test_similar_setup_result_accepts_none_grade_at_pick():
    """Crash 2: SimilarSetupResult must accept None for match_grade_at_pick."""
    result = SimilarSetupResult(
        query_symbol="000001.SZ",
        match_symbol="000002.SZ",
        match_trading_day="2026-06-06",
        similarity=0.85,
        match_grade_at_pick=None,
    )

    assert result.match_grade_at_pick is None
