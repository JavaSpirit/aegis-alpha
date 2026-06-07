from __future__ import annotations

from aegis_alpha.feedback.attribution import (
    AttributionInputs,
    attribute_outcome,
)


def test_leader_break_down_when_theme_role_follower_and_leader_broke() -> None:
    inputs = AttributionInputs(
        symbol="F1",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="follower",
        theme_leader_symbol="LDR",
        theme_leader_final_status="broken",
        market_break_board_rate=0.2,  # below _HIGH_BREAK_BOARD_RATE (0.45); Rule 1 must not fire
        auction_change_pct=2.0,
        first_limit_up_time="09:50:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "leader_break_down"
    assert any("LDR" in line for line in attribution.evidence)


def test_high_break_board_environment_dominates_other_signals() -> None:
    inputs = AttributionInputs(
        symbol="X",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="X",
        theme_leader_final_status="sealed",
        market_break_board_rate=0.5,  # at/above 0.45 threshold → Rule 1 fires
        auction_change_pct=1.0,
        first_limit_up_time="09:30:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "high_break_board_environment"


def test_auction_high_open_too_far_threshold() -> None:
    inputs = AttributionInputs(
        symbol="Y",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="Y",
        theme_leader_final_status="broken",
        market_break_board_rate=0.2,
        auction_change_pct=4.5,
        first_limit_up_time="10:00:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    # theme_role="leader" can't trigger leader_break_down (that rule needs follower/co_leader),
    # so auction_high_open_too_far is the only reachable result.
    assert attribution.primary_tag == "auction_high_open_too_far"


def test_no_clear_attribution_when_sealed() -> None:
    inputs = AttributionInputs(
        symbol="Z",
        trading_day="2026-05-31",
        sealed_second_board=True,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="Z",
        theme_leader_final_status="sealed",
        market_break_board_rate=0.2,
        auction_change_pct=2.0,
        first_limit_up_time="09:35:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "no_clear_attribution"


def test_first_seal_too_late_when_after_10_30() -> None:
    inputs = AttributionInputs(
        symbol="W",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="W",
        theme_leader_final_status="reopened",
        market_break_board_rate=0.2,
        auction_change_pct=1.5,
        first_limit_up_time="13:45:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "first_seal_too_late"


def test_seal_amount_decay_fires_when_above_threshold() -> None:
    inputs = AttributionInputs(
        symbol="S",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="S",
        theme_leader_final_status="sealed",
        market_break_board_rate=0.2,
        auction_change_pct=1.0,
        first_limit_up_time="09:30:00",
        seal_decay_pct=35.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "seal_amount_decay"
    assert any("35.0" in line for line in attribution.evidence)


def test_no_clear_attribution_when_no_signal_matches() -> None:
    inputs = AttributionInputs(
        symbol="N",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="N",
        theme_leader_final_status="sealed",
        market_break_board_rate=0.2,
        auction_change_pct=0.5,
        first_limit_up_time="09:20:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "no_clear_attribution"
    assert any("No clear attribution" in line for line in attribution.evidence)


def test_secondary_tags_collected_alongside_primary() -> None:
    # Primary should be leader_break_down; auction_change_pct also above threshold,
    # so it must appear in secondary_tags.
    inputs = AttributionInputs(
        symbol="F",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="follower",
        theme_leader_symbol="LDR",
        theme_leader_final_status="broken",
        market_break_board_rate=0.2,
        auction_change_pct=4.5,
        first_limit_up_time="09:30:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "leader_break_down"
    assert "auction_high_open_too_far" in attribution.secondary_tags


def _make_failed_seal_inputs(market_break_board_rate: float) -> AttributionInputs:
    """Helper: failed-seal candidate with no other rule firing except possibly Rule 1."""
    return AttributionInputs(
        symbol="B",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",  # not follower/co_leader → Rule 2 cannot fire
        theme_leader_symbol="B",
        theme_leader_final_status="sealed",  # leader did not break → Rule 2 cannot fire
        market_break_board_rate=market_break_board_rate,
        auction_change_pct=1.0,  # below 3.0 → Rule 4 cannot fire
        first_limit_up_time="09:30:00",  # before 10:30 → Rule 5 cannot fire
        seal_decay_pct=0.0,  # below 30.0 → Rule 3 cannot fire
        previous_consecutive_boards=1,
    )


def test_break_board_rule1_boundary() -> None:
    """0.45 is inclusive (>= threshold fires); 0.44 is just below (must not fire)."""
    below = _make_failed_seal_inputs(market_break_board_rate=0.44)
    at_threshold = _make_failed_seal_inputs(market_break_board_rate=0.45)

    result_below = attribute_outcome(below)
    result_at = attribute_outcome(at_threshold)

    assert result_below.primary_tag != "high_break_board_environment", (
        "rate=0.44 is below _HIGH_BREAK_BOARD_RATE (0.45); Rule 1 must NOT fire"
    )
    assert result_at.primary_tag == "high_break_board_environment", (
        "rate=0.45 equals _HIGH_BREAK_BOARD_RATE (0.45); Rule 1 MUST fire (>= is inclusive)"
    )
