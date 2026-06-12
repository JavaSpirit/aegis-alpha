"""TDD guard for AgentJudgmentScorecard + AgentJudgmentRow — calibration metrics only, no program grade."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aegis_alpha.models import (
    AgentJudgmentRow,
    AgentJudgmentScorecard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recursive_keys(obj: object) -> set[str]:
    """Walk any nested dict/list and collect every dict key."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _recursive_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _recursive_keys(item)
    return keys


def _make_scorecard() -> AgentJudgmentScorecard:
    rows = [
        AgentJudgmentRow(
            symbol="000001",
            trading_day="2026-06-01",
            predicted_grade="A",
            predicted_likelihood="high",
            sealed_second_board=True,
            next_day_open_pct=9.8,
            next_day_high_pct=10.0,
        ),
        AgentJudgmentRow(
            symbol="300750",
            trading_day="2026-06-02",
            predicted_grade="B",
            predicted_likelihood="medium",
            sealed_second_board=False,
            next_day_open_pct=2.5,
            next_day_high_pct=3.1,
        ),
        AgentJudgmentRow(
            symbol="002415",
            trading_day="2026-06-03",
            predicted_grade="C",
            predicted_likelihood="low",
            sealed_second_board=None,  # outcome not yet recorded
        ),
    ]
    return AgentJudgmentScorecard(
        start_day="2026-06-01",
        end_day="2026-06-03",
        sample_size=2,
        brier_score=0.28,
        likelihood_calibration={
            "high": {"predicted_rate": 0.8, "realized_seal_rate": 1.0, "n": 1.0},
            "medium": {"predicted_rate": 0.5, "realized_seal_rate": 0.0, "n": 1.0},
            "low": {"predicted_rate": 0.2, "realized_seal_rate": 0.0, "n": 0.0},
        },
        grade_hit_rate={
            "A": {"realized_seal_rate": 1.0, "n": 1.0},
            "B": {"realized_seal_rate": 0.0, "n": 1.0},
            "C": {"realized_seal_rate": 0.0, "n": 0.0},
        },
        rows=rows,
        notes=["2-day window, small sample"],
    )


# ---------------------------------------------------------------------------
# Construction + round-trip
# ---------------------------------------------------------------------------

def test_scorecard_constructs_and_dumps() -> None:
    sc = _make_scorecard()
    dumped = sc.model_dump()

    assert dumped["start_day"] == "2026-06-01"
    assert dumped["end_day"] == "2026-06-03"
    assert dumped["sample_size"] == 2
    assert abs(dumped["brier_score"] - 0.28) < 1e-9
    assert len(dumped["rows"]) == 3
    assert "disclaimer" in dumped


def test_scorecard_rows_round_trip() -> None:
    sc = _make_scorecard()
    dumped = sc.model_dump()

    row0 = dumped["rows"][0]
    assert row0["symbol"] == "000001"
    assert row0["predicted_grade"] == "A"
    assert row0["predicted_likelihood"] == "high"
    assert row0["sealed_second_board"] is True

    row2 = dumped["rows"][2]
    assert row2["sealed_second_board"] is None  # not yet known


def test_scorecard_nested_dicts_round_trip() -> None:
    sc = _make_scorecard()
    dumped = sc.model_dump()

    cal = dumped["likelihood_calibration"]
    assert "high" in cal
    assert abs(cal["high"]["realized_seal_rate"] - 1.0) < 1e-9
    assert abs(cal["high"]["n"] - 1.0) < 1e-9

    ghr = dumped["grade_hit_rate"]
    assert "A" in ghr
    assert abs(ghr["A"]["realized_seal_rate"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Empty / zero-sample scorecard is valid
# ---------------------------------------------------------------------------

def test_empty_scorecard_is_valid() -> None:
    sc = AgentJudgmentScorecard(
        start_day="2026-06-01",
        end_day="2026-06-01",
    )
    dumped = sc.model_dump()

    assert dumped["sample_size"] == 0
    assert dumped["brier_score"] is None
    assert dumped["rows"] == []
    assert dumped["likelihood_calibration"] == {}
    assert dumped["grade_hit_rate"] == {}


# ---------------------------------------------------------------------------
# Philosophy guard: no program-recommendation / grading fields anywhere
# ---------------------------------------------------------------------------

def test_scorecard_no_program_grade_fields() -> None:
    """Scorecard must contain ONLY calibration metrics and raw joined facts — no program advice."""
    sc = _make_scorecard()
    dumped = sc.model_dump()

    banned = {
        "recommendation",
        "advice",
        "program_grade",
        "action",
        "suggested_patch",
        "buy",
        "sell",
    }
    all_keys = _recursive_keys(dumped)
    found = banned & all_keys
    assert not found, f"Banned grading/recommendation fields found in scorecard dump: {found}"


# ---------------------------------------------------------------------------
# Validation: predicted_likelihood only accepts {"high", "medium", "low"}
# ---------------------------------------------------------------------------

def test_predicted_likelihood_invalid_value_raises() -> None:
    with pytest.raises(ValidationError):
        AgentJudgmentRow(
            symbol="000001",
            trading_day="2026-06-01",
            predicted_likelihood="very_high",  # type: ignore[arg-type]
        )


def test_predicted_likelihood_valid_values() -> None:
    for val in ("high", "medium", "low"):
        row = AgentJudgmentRow(
            symbol="000001",
            trading_day="2026-06-01",
            predicted_likelihood=val,  # type: ignore[arg-type]
        )
        assert row.predicted_likelihood == val


def test_predicted_likelihood_none_is_valid() -> None:
    row = AgentJudgmentRow(symbol="000001", trading_day="2026-06-01")
    assert row.predicted_likelihood is None
    assert row.predicted_grade is None


# ---------------------------------------------------------------------------
# Validation: predicted_grade only accepts {"A","B","C","REJECT"}
# ---------------------------------------------------------------------------

def test_predicted_grade_invalid_value_raises() -> None:
    with pytest.raises(ValidationError):
        AgentJudgmentRow(
            symbol="000001",
            trading_day="2026-06-01",
            predicted_grade="Z",  # type: ignore[arg-type]
        )
