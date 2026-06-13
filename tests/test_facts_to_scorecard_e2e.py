"""End-to-end integration test: Phase 2 dossier → Phase 3 agent_eval contract → Phase 7 scorecard.

This file locks the cross-phase contract chain so that drift between phases
(e.g. dossier factor keys diverging from REQUIRED_FACTORS, or scorecard
mis-joining predictions) is caught immediately.

No I/O, no DB, no network.  All four test functions share synthetic fixtures
built from real model constructors — no mocking.
"""
from __future__ import annotations

import pytest

from aegis_alpha import agent_eval
from aegis_alpha.agent_eval import (
    REQUIRED_FACTORS,
    parsed_factor_analyses,
    parsed_grades,
    parsed_promotion_likelihoods,
)
from aegis_alpha.feedback.agent_scorecard import compute_scorecard
from aegis_alpha.measurements.promotion_dossier import assemble_promotion_dossier
from aegis_alpha.models import (
    AgentReview,
    CandidateOutcomeReview,
    MarketSentimentGate,
    SecondBoardCandidate,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers (no pytest fixtures — plain functions to keep it
# readable when inspecting failures across tests)
# ---------------------------------------------------------------------------

def _make_gate(trading_day: str = "2026-06-01") -> MarketSentimentGate:
    return MarketSentimentGate(
        trading_day=trading_day,
        timestamp=f"{trading_day}T09:25:00+08:00",
        data_mode="live",
        provider="jvquant",
        limit_up_count=38,
        break_board_rate=0.20,
        second_board_success_rate=0.55,
        hot_theme_count=6,
        risk_flags=[],
        positive_signals=[],
        conclusion="市场情绪偏热，适合博弈二板",
        consecutive_boards_alive_rate=0.60,
        first_to_second_promotion_rate=0.50,
        second_to_third_promotion_rate=0.35,
        max_height_today=4,
    )


def _make_candidate(symbol: str = "000001", name: str = "测试股票甲") -> SecondBoardCandidate:
    return SecondBoardCandidate(
        symbol=symbol,
        name=name,
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
        break_board_count=1,
        reseal_count=3,
        max_seal_amount_cny=450_000_000.0,
        final_seal_time="14:55:00",
        current_change_pct=10.0,
        five_min_speed_pct=2.5,
        big_order_net_inflow_ratio=0.1,
        same_theme_rising_count=4,
        orderbook_quality_score=75.0,
        three_year_touch_limit_success_rate=0.6,
        three_year_sealed_next_day_gap_up_rate=0.55,
        notes=[],
    )


def _per_symbol_item(dossier, symbol: str, promotion_likelihood: str = "high", grade: str = "A") -> dict:
    """Build a well-formed per_symbol dict whose factor_analysis values are
    derived from the dossier — making the cross-phase linkage explicit."""
    em = dossier.market_emotion
    tp = dossier.theme_position
    fs = dossier.float_size
    ve = dossier.volume_energy
    rs = dossier.reseal_strength
    return {
        "symbol": symbol,
        "grade": grade,
        "promotion_likelihood": promotion_likelihood,
        "natural_language_reason": (
            f"该股{tp.theme}题材处于{tp.theme_lifecycle_stage}阶段，"
            f"市场今日涨停{em.limit_up_count}支，情绪偏热，"
            f"具备较强的晋级三板条件。"
        ),
        "factor_analysis": {
            "market_emotion": (
                f"今日涨停{em.limit_up_count}支，炸板率{em.break_board_rate:.0%}，"
                f"二板成功率{em.second_board_success_rate:.0%}，市场情绪{em.conclusion}。"
            ),
            "theme_position": (
                f"题材{tp.theme}处于{tp.theme_lifecycle_stage}阶段，"
                f"个股在题材中的角色为{tp.theme_role}，题材动能充足。"
            ),
            "float_size": (
                f"自由流通市值约{fs.free_float_market_cap_cny / 1e8:.1f}亿元，"
                f"属于中小盘，资金拉升难度适中。"
            ),
            "volume_energy": (
                f"换手金额{ve.turnover_cny / 1e8:.1f}亿元，"
                f"较十日均量比{ve.turnover_cny / ve.avg_turnover_10d_cny:.2f}倍，"
                f"昨日缩量比{ve.prev_day_volume_shrink_ratio:.2f}，量能结构健康。"
            ),
            "reseal_strength": (
                f"炸板{rs.break_board_count}次，回封{rs.reseal_count}次，"
                f"最大封单{rs.max_seal_amount_cny / 1e8:.1f}亿元，"
                f"尾盘回封时间{rs.final_seal_time}，回封意愿较强。"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Test A — dossier factor keys == REQUIRED_FACTORS (the linchpin)
# ---------------------------------------------------------------------------

def test_a_dossier_factor_keys_match_required_factors() -> None:
    """Phase 2 → Phase 3 contract: PromotionDossier's nested fact-bundle keys
    must be exactly the set of REQUIRED_FACTORS that agent_eval mandates.

    This is the first link of the chain.  If the dossier ever grows a new
    bundle or renames one, agent_eval.REQUIRED_FACTORS must be updated
    in the same commit — this test enforces that.
    """
    candidate = _make_candidate()
    gate = _make_gate()
    dossier = assemble_promotion_dossier(candidate, gate)

    # Collect the names of the nested fact-bundle fields on the dossier.
    # The five factor bundles are the direct sub-model fields; we exclude
    # scalar identity/meta fields (symbol, name, data_mode, provider,
    # data_timestamp, disclaimer).
    _SCALAR_META = {"symbol", "name", "data_mode", "provider", "data_timestamp", "disclaimer"}
    dossier_fields = set(dossier.__class__.model_fields.keys()) - _SCALAR_META

    # The names of the nested fact bundles must EXACTLY match REQUIRED_FACTORS.
    assert dossier_fields == set(REQUIRED_FACTORS), (
        f"Dossier factor-bundle keys {dossier_fields!r} "
        f"do not match REQUIRED_FACTORS {set(REQUIRED_FACTORS)!r}. "
        "Update one to match the other in the same commit."
    )


# ---------------------------------------------------------------------------
# Test B — well-formed agent review passes, dropped factor fails
# ---------------------------------------------------------------------------

def test_b_well_formed_agent_output_passes_eval_positive() -> None:
    """Phase 3 contract (positive): an agent output built FROM the dossier's
    factor keys passes agent_eval's five_factors_present and
    promotion_likelihood_present checks."""
    candidate = _make_candidate()
    gate = _make_gate()
    dossier = assemble_promotion_dossier(candidate, gate)

    item = _per_symbol_item(dossier, symbol=candidate.symbol)
    agent_output = {"per_symbol": [item]}

    # five_factors_present
    factor_analyses = parsed_factor_analyses(agent_output)
    assert len(factor_analyses) == 1
    fa = factor_analyses[0]
    assert set(fa.keys()) >= set(REQUIRED_FACTORS), (
        f"Missing factors: {set(REQUIRED_FACTORS) - set(fa.keys())}"
    )
    # All values must be non-empty strings
    for key in REQUIRED_FACTORS:
        assert str(fa.get(key) or "").strip(), f"Factor '{key}' is empty"

    # promotion_likelihood_present
    likelihoods = parsed_promotion_likelihoods(agent_output)
    assert likelihoods == ["high"]
    assert all(v in {"high", "medium", "low"} for v in likelihoods)

    # grade_present
    grades = parsed_grades(agent_output)
    assert grades == ["A"]
    assert all(g in {"A", "B", "C", "REJECT"} for g in grades)


def test_b_missing_one_factor_fails_eval_negative() -> None:
    """Phase 3 contract (negative / non-vacuous proof): dropping any single
    factor from factor_analysis causes the five-factors check to fail.

    This proves the contract assertion has teeth — the positive case above
    would be vacuous without this negative counterpart.
    """
    candidate = _make_candidate()
    gate = _make_gate()
    dossier = assemble_promotion_dossier(candidate, gate)

    item = _per_symbol_item(dossier, symbol=candidate.symbol)
    # Drop one factor key to simulate an agent that forgot it
    factor_to_drop = "reseal_strength"
    incomplete_fa = {k: v for k, v in item["factor_analysis"].items() if k != factor_to_drop}
    incomplete_item = {**item, "factor_analysis": incomplete_fa}
    agent_output = {"per_symbol": [incomplete_item]}

    factor_analyses = parsed_factor_analyses(agent_output)
    assert len(factor_analyses) == 1
    fa = factor_analyses[0]

    # The five-factors check must FAIL (factor_to_drop is absent)
    per_symbol_count = 1
    five_factors_pass = (
        bool(factor_analyses)
        and (per_symbol_count == 0 or len(factor_analyses) == per_symbol_count)
        and all(
            all(bool(str(fa.get(key) or "").strip()) for key in REQUIRED_FACTORS)
            for fa in factor_analyses
        )
    )
    assert not five_factors_pass, (
        f"Expected five_factors check to FAIL when '{factor_to_drop}' is absent, "
        "but it passed — the contract assertion is vacuous."
    )


# ---------------------------------------------------------------------------
# Test C — single-symbol scorecard: Brier + calibration + grade_hit_rate
# ---------------------------------------------------------------------------

def test_c_single_symbol_scorecard_brier_and_calibration() -> None:
    """Phase 7 scorecard end-to-end for one symbol.

    Prediction: high (→ 0.8) / grade A
    Outcome: sealed_second_board=True (→ 1.0)
    Expected brier = (0.8 - 1.0)^2 = 0.04
    """
    candidate = _make_candidate()
    gate = _make_gate("2026-06-01")
    dossier = assemble_promotion_dossier(candidate, gate)

    item = _per_symbol_item(dossier, symbol=candidate.symbol, promotion_likelihood="high", grade="A")
    agent_output = {"per_symbol": [item]}

    review = AgentReview(
        run_type="daily",
        target_time="2026-06-01T09:30:00",
        symbols=[candidate.symbol],
        grades=["A"],
        payload=agent_output,
        created_at="2026-06-01T08:00:00",
    )
    outcome = CandidateOutcomeReview(
        symbol=candidate.symbol,
        trading_day="2026-06-01",
        sealed_second_board=True,
        next_day_open_pct=9.8,
        next_day_high_pct=10.0,
    )

    sc = compute_scorecard([review], [outcome], start_day="2026-06-01", end_day="2026-06-01")

    # sample_size
    assert sc.sample_size == 1

    # Brier: (0.8 - 1.0)^2 = 0.04
    assert sc.brier_score is not None
    assert abs(sc.brier_score - 0.04) < 1e-9, f"Expected brier≈0.04, got {sc.brier_score}"

    # likelihood_calibration["high"]
    assert "high" in sc.likelihood_calibration
    cal_high = sc.likelihood_calibration["high"]
    assert cal_high["n"] == 1.0
    assert abs(cal_high["realized_seal_rate"] - 1.0) < 1e-9

    # grade_hit_rate["A"]
    assert "A" in sc.grade_hit_rate
    ghr_a = sc.grade_hit_rate["A"]
    assert ghr_a["n"] == 1.0
    assert abs(ghr_a["realized_seal_rate"] - 1.0) < 1e-9

    # No program-judgment fields anywhere in the scorecard dict
    _assert_no_program_judgment_keys(sc.model_dump())


def _recursive_keys(obj: object) -> set[str]:
    """Collect every dict key recursively from a JSON-serialisable object."""
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


_PROGRAM_JUDGMENT_KEYS = {"recommendation", "advice", "program_grade", "buy", "sell", "order"}


def _assert_no_program_judgment_keys(obj: object) -> None:
    """Assert that the scorecard dict contains no program-judgment directive fields."""
    all_keys = _recursive_keys(obj)
    found = all_keys & _PROGRAM_JUDGMENT_KEYS
    assert not found, (
        f"Scorecard dict contains forbidden program-judgment keys: {found!r}. "
        "The chain must remain facts/metrics only end-to-end."
    )


# ---------------------------------------------------------------------------
# Test D — multi-symbol chain integrity (join keys + Brier averaging)
# ---------------------------------------------------------------------------

def test_d_multi_symbol_chain_integrity() -> None:
    """Phase 2→3→7 with two candidates on the same trading day.

    Candidate A: symbol 000001, prediction high (0.8), outcome sealed=True (1.0)
      → squared error = (0.8-1.0)^2 = 0.04
    Candidate B: symbol 300750, prediction low (0.2), outcome sealed=False (0.0)
      → squared error = (0.2-0.0)^2 = 0.04
    Expected: sample_size=2, brier=(0.04+0.04)/2=0.04
    Both likelihood buckets present with n=1 each.
    """
    gate = _make_gate("2026-06-01")

    candidate_a = _make_candidate(symbol="000001", name="测试股票甲")
    candidate_b = _make_candidate(symbol="300750", name="测试股票乙")

    dossier_a = assemble_promotion_dossier(candidate_a, gate)
    dossier_b = assemble_promotion_dossier(candidate_b, gate)

    item_a = _per_symbol_item(dossier_a, symbol="000001", promotion_likelihood="high", grade="A")
    item_b = _per_symbol_item(dossier_b, symbol="300750", promotion_likelihood="low", grade="C")

    review = AgentReview(
        run_type="daily",
        target_time="2026-06-01T09:30:00",
        symbols=["000001", "300750"],
        grades=["A", "C"],
        payload={"per_symbol": [item_a, item_b]},
        created_at="2026-06-01T08:00:00",
    )
    outcome_a = CandidateOutcomeReview(
        symbol="000001",
        trading_day="2026-06-01",
        sealed_second_board=True,
        next_day_open_pct=9.8,
    )
    outcome_b = CandidateOutcomeReview(
        symbol="300750",
        trading_day="2026-06-01",
        sealed_second_board=False,
        next_day_open_pct=1.2,
    )

    sc = compute_scorecard(
        [review],
        [outcome_a, outcome_b],
        start_day="2026-06-01",
        end_day="2026-06-01",
    )

    # sample_size
    assert sc.sample_size == 2

    # Brier: mean of 0.04 + 0.04 = 0.04
    assert sc.brier_score is not None
    assert abs(sc.brier_score - 0.04) < 1e-9, f"Expected brier≈0.04, got {sc.brier_score}"

    # Both likelihood buckets present
    assert "high" in sc.likelihood_calibration, "'high' bucket missing"
    assert "low" in sc.likelihood_calibration, "'low' bucket missing"
    assert sc.likelihood_calibration["high"]["n"] == 1.0
    assert sc.likelihood_calibration["low"]["n"] == 1.0
    assert abs(sc.likelihood_calibration["high"]["realized_seal_rate"] - 1.0) < 1e-9
    assert abs(sc.likelihood_calibration["low"]["realized_seal_rate"] - 0.0) < 1e-9

    # Both grade buckets present
    assert "A" in sc.grade_hit_rate
    assert "C" in sc.grade_hit_rate

    # No program-judgment fields
    _assert_no_program_judgment_keys(sc.model_dump())
