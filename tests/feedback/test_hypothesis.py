def test_simulate_outcome_changes_grade_when_seal_amount_doubled(tmp_path):
    """If we hypothesize the seal amount is 2x larger, the rule may upgrade grade.
    With the existing payload (only seal_amount + 5min speed, no inflow/orderbook),
    candidate_grade returns C for the hypothetical. We still receive a structured
    comparison."""
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
    assert out.hypothetical_grade == "C"


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
    """A seal-only crossing no longer bumps grade by heuristic.

    P8 uses candidate_grade(), so missing inflow/orderbook/theme fields keep
    this hypothetical at C despite the larger seal amount.
    """
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
    assert out.hypothetical_grade == "C"


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


def test_simulate_outcome_uses_real_candidate_grade_for_a_grade_inputs():
    """When all of seal/speed/inflow/orderbook/theme_count clear A thresholds,
    candidate_grade returns 'A' and simulate_outcome must reflect that."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X",
        trading_day="2026-05-30",
        grade_at_pick="C",
        grade_reason="",
        theme="AI",
        theme_role="leader",
        previous_consecutive_boards=2,
        payload_json=(
            '{"action": "active",'
            ' "change_pct": 5.0,'
            ' "five_min_speed_pct": 1.0,'
            ' "big_order_net_inflow_ratio": 0.05,'
            ' "orderbook_quality_score": 50.0,'
            ' "same_theme_rising_count": 1,'
            ' "first_limit_up_time": "09:32:00",'
            ' "seal_amount_cny": 100000000.0,'
            ' "seal_to_turnover_ratio": 0.5}'
        ),
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={
                "change_pct": 9.5,
                "five_min_speed_pct": 4.0,
                "big_order_net_inflow_ratio": 0.30,
                "orderbook_quality_score": 75.0,
                "same_theme_rising_count": 5,
                "seal_amount_cny": 800_000_000.0,
                "seal_to_turnover_ratio": 3.0,
            },
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    assert out.hypothetical_grade == "A"


def test_simulate_outcome_uses_real_candidate_grade_for_reject_when_action_avoid():
    """When action=avoid, candidate_grade always returns REJECT regardless of metrics."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X",
        trading_day="2026-05-30",
        grade_at_pick="B",
        grade_reason="",
        theme="AI",
        theme_role="leader",
        previous_consecutive_boards=2,
        payload_json=(
            '{"action": "active",'
            ' "change_pct": 9.0,'
            ' "five_min_speed_pct": 4.0,'
            ' "big_order_net_inflow_ratio": 0.20,'
            ' "orderbook_quality_score": 70.0,'
            ' "same_theme_rising_count": 4,'
            ' "first_limit_up_time": "09:32:00",'
            ' "seal_amount_cny": 300000000.0,'
            ' "seal_to_turnover_ratio": 2.0}'
        ),
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"action": "avoid"},
        )
    )
    assert out is not None
    assert out.original_grade == "B"
    assert out.hypothetical_grade == "REJECT"
