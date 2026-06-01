def test_simulate_outcome_changes_grade_when_seal_amount_doubled(tmp_path):
    """If we hypothesize the seal amount is 2x larger, the rule may upgrade grade.
    With the existing P4 rule_changes (no auto-upgrade), grade stays 'B' but
    we still receive a structured comparison."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="600519", trading_day="2026-05-30", grade_at_pick="B",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0, "five_min_speed_pct": 2.5}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 200_000_000.0},
        )
    )
    assert out.original_grade == "B"
    assert out.applied_hypothesis == {"seal_amount_cny": 200_000_000.0}
    assert "seal_amount_cny" in out.payload_diff


def test_simulate_outcome_returns_none_when_snapshot_payload_invalid():
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="Y", theme_role="follower",
        previous_consecutive_boards=0,
        payload_json="not valid json",
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(snapshot=snap, hypothesis={"seal_amount_cny": 1})
    )
    assert out is None


def test_simulate_outcome_promotes_grade_when_seal_amount_doubles_above_threshold():
    """When the hypothesis pushes seal_amount_cny across 5亿, the hypothetical
    grade should be one notch up. Starting C → expect B."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0, "five_min_speed_pct": 2.5}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 600_000_000.0},
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    assert out.hypothetical_grade == "B"


def test_simulate_outcome_keeps_grade_when_hypothesis_does_not_cross_threshold():
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 200_000_000.0},  # still below 5亿
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    assert out.hypothetical_grade == "C"
