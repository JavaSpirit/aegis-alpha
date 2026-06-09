from __future__ import annotations

import pytest

from aegis_alpha.models import (
    MarketSentimentGate,
    SecondBoardCandidate,
)
from aegis_alpha.measurements.promotion_dossier import assemble_promotion_dossier


# ---------------------------------------------------------------------------
# Sentinel helpers — distinct numeric and string values to prove no mixup
# ---------------------------------------------------------------------------

def _make_gate() -> MarketSentimentGate:
    return MarketSentimentGate(
        trading_day="2026-06-09",
        timestamp="2026-06-09T09:25:00+08:00",
        data_mode="live",
        provider="jvquant",
        limit_up_count=42,
        break_board_rate=0.25,
        second_board_success_rate=0.60,
        hot_theme_count=7,
        risk_flags=[],
        positive_signals=[],
        conclusion="市场情绪偏热",
        consecutive_boards_alive_rate=0.55,
        first_to_second_promotion_rate=0.48,
        second_to_third_promotion_rate=0.33,
        max_height_today=5,
    )


def _make_candidate() -> SecondBoardCandidate:
    return SecondBoardCandidate(
        symbol="000001",
        name="测试股票",
        data_mode="live",
        provider="jvquant",
        theme="AI算力",
        previous_limit_up_time="09:30:00",
        theme_lifecycle_stage="climax",
        theme_role="leader",
        free_float_market_cap_cny=8_500_000_000.0,
        turnover_cny=1_200_000_000.0,
        avg_turnover_10d_cny=900_000_000.0,
        prev_day_volume_shrink_ratio=0.72,
        break_board_count=2,
        reseal_count=3,
        max_seal_amount_cny=450_000_000.0,
        final_seal_time="14:55:00",
        # required fields with sentinel values
        current_change_pct=10.0,
        five_min_speed_pct=2.5,
        big_order_net_inflow_ratio=0.1,
        same_theme_rising_count=4,
        orderbook_quality_score=75.0,
        three_year_touch_limit_success_rate=0.6,
        three_year_sealed_next_day_gap_up_rate=0.55,
        notes=[],
    )


# ---------------------------------------------------------------------------
# 1. Field-mapping table test
# ---------------------------------------------------------------------------

def test_field_mapping_verbatim():
    """Every dossier field must be an exact copy of its source field."""
    candidate = _make_candidate()
    gate = _make_gate()

    dossier = assemble_promotion_dossier(candidate, gate)

    # Top-level identity fields from candidate
    assert dossier.symbol == candidate.symbol
    assert dossier.name == candidate.name
    assert dossier.data_mode == candidate.data_mode
    assert dossier.provider == candidate.provider

    # data_timestamp comes from gate.timestamp (the market read time)
    assert dossier.data_timestamp == gate.timestamp

    # market_emotion — all 10 fields from gate
    em = dossier.market_emotion
    assert em.trading_day == gate.trading_day
    assert em.limit_up_count == gate.limit_up_count
    assert em.break_board_rate == gate.break_board_rate
    assert em.second_board_success_rate == gate.second_board_success_rate
    assert em.consecutive_boards_alive_rate == gate.consecutive_boards_alive_rate
    assert em.first_to_second_promotion_rate == gate.first_to_second_promotion_rate
    assert em.second_to_third_promotion_rate == gate.second_to_third_promotion_rate
    assert em.max_height_today == gate.max_height_today
    assert em.hot_theme_count == gate.hot_theme_count
    assert em.conclusion == gate.conclusion

    # theme_position from candidate
    tp = dossier.theme_position
    assert tp.theme == candidate.theme
    assert tp.theme_lifecycle_stage == candidate.theme_lifecycle_stage
    assert tp.theme_role == candidate.theme_role

    # float_size from candidate
    fs = dossier.float_size
    assert fs.free_float_market_cap_cny == candidate.free_float_market_cap_cny

    # volume_energy from candidate
    ve = dossier.volume_energy
    assert ve.turnover_cny == candidate.turnover_cny
    assert ve.avg_turnover_10d_cny == candidate.avg_turnover_10d_cny
    assert ve.prev_day_volume_shrink_ratio == candidate.prev_day_volume_shrink_ratio

    # reseal_strength from candidate
    rs = dossier.reseal_strength
    assert rs.break_board_count == candidate.break_board_count
    assert rs.reseal_count == candidate.reseal_count
    assert rs.max_seal_amount_cny == candidate.max_seal_amount_cny
    assert rs.final_seal_time == candidate.final_seal_time


# ---------------------------------------------------------------------------
# 2. Immutability test
# ---------------------------------------------------------------------------

def test_inputs_are_not_mutated():
    """The assembler must not modify either input object."""
    candidate = _make_candidate()
    gate = _make_gate()

    candidate_snapshot = candidate.model_dump()
    gate_snapshot = gate.model_dump()

    assemble_promotion_dossier(candidate, gate)

    assert candidate.model_dump() == candidate_snapshot
    assert gate.model_dump() == gate_snapshot


# ---------------------------------------------------------------------------
# 3. Philosophy guard — no judgment fields anywhere in the dossier
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "grade",
    "grade_reason",
    "probability",
    "promotion_likelihood",
    "score",
    "estimated_seal_probability",
}


def _recursive_keys(obj: object) -> set[str]:
    """Collect every dict key, recursively, from a JSON-serialisable object."""
    if isinstance(obj, dict):
        keys: set[str] = set(obj.keys())
        for v in obj.values():
            keys |= _recursive_keys(v)
        return keys
    if isinstance(obj, list):
        keys = set()
        for item in obj:
            keys |= _recursive_keys(item)
        return keys
    return set()


def test_no_judgment_fields_in_dossier():
    """The dossier must contain none of the forbidden judgment/score keys."""
    candidate = _make_candidate()
    gate = _make_gate()

    dossier = assemble_promotion_dossier(candidate, gate)
    all_keys = _recursive_keys(dossier.model_dump())

    forbidden_found = all_keys & _FORBIDDEN_KEYS
    assert not forbidden_found, f"Found forbidden judgment keys: {forbidden_found}"


# ---------------------------------------------------------------------------
# 4. No fabricated facts: timestamp and disclaimer
# ---------------------------------------------------------------------------

def test_data_timestamp_equals_gate_timestamp():
    """data_timestamp must be gate.timestamp — not a newly generated timestamp."""
    candidate = _make_candidate()
    gate = _make_gate()

    dossier = assemble_promotion_dossier(candidate, gate)
    assert dossier.data_timestamp == gate.timestamp


def test_disclaimer_is_model_default():
    """disclaimer must be non-empty and contain 'Facts-only' (the model default)."""
    candidate = _make_candidate()
    gate = _make_gate()

    dossier = assemble_promotion_dossier(candidate, gate)
    assert dossier.disclaimer, "disclaimer must be non-empty"
    assert "Facts-only" in dossier.disclaimer, (
        f"disclaimer must contain 'Facts-only'; got: {dossier.disclaimer!r}"
    )
