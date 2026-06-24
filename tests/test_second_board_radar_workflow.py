"""End-to-end smoke test for the second-board-radar skill workflow.

Covers the full chain with synthetic mock data:
  1. Market sentiment gate (hot / cautious / hostile)
  2. Second-board candidates in all 5 lifecycle stages
  3. PromotionDossier assembly
  4. Agent response following SKILL.md lifecycle-downgrade rules
  5. agent_eval validation (evaluate_agent_replay_response)
  6. Scorecard computation

No I/O, no DB, no network — pure in-process fixture pipeline.
"""
from __future__ import annotations

import copy
import json
import textwrap

import pytest

from aegis_alpha import agent_eval
from aegis_alpha.agent_eval import (
    REQUIRED_FACTORS,
    evaluate_agent_replay_response,
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

# ═══════════════════════════════════════════════════════════════════════════
# Shared fixture helpers
# ═══════════════════════════════════════════════════════════════════════════

# ── Market gates (3 scenarios) ─────────────────────────────────────────────

def _make_gate_hot() -> MarketSentimentGate:
    """火热市场：涨停多、炸板率低、题材广泛，适合进攻。"""
    return MarketSentimentGate(
        trading_day="2026-06-15",
        timestamp="2026-06-15T09:25:00+08:00",
        data_mode="live",
        provider="jvquant",
        limit_up_count=52,
        break_board_rate=0.12,
        second_board_success_rate=0.65,
        hot_theme_count=5,
        risk_flags=[],
        positive_signals=["涨停家数 > 50", "炸板率 < 15%", "热点题材 > 3"],
        conclusion="市场情绪偏暖，环境支持选择性打板。",
        yesterday_limitup_today_premium_pct=1.8,
        consecutive_boards_alive_rate=0.72,
        first_to_second_promotion_rate=0.55,
        second_to_third_promotion_rate=0.38,
        max_height_today=5,
    )


def _make_gate_cautious() -> MarketSentimentGate:
    """谨慎市场：涨停适中、炸板率中等，需精选。"""
    return MarketSentimentGate(
        trading_day="2026-06-16",
        timestamp="2026-06-16T09:25:00+08:00",
        data_mode="live",
        provider="jvquant",
        limit_up_count=28,
        break_board_rate=0.22,
        second_board_success_rate=0.45,
        hot_theme_count=2,
        risk_flags=["炸板率偏高(22%)"],
        positive_signals=["连板存活率尚可"],
        conclusion="市场环境中性偏谨慎，需精选个股。",
        yesterday_limitup_today_premium_pct=0.3,
        consecutive_boards_alive_rate=0.55,
        first_to_second_promotion_rate=0.40,
        second_to_third_promotion_rate=0.25,
        max_height_today=3,
    )


def _make_gate_hostile() -> MarketSentimentGate:
    """不利市场：涨停少、炸板率高，应观望。"""
    return MarketSentimentGate(
        trading_day="2026-06-17",
        timestamp="2026-06-17T09:25:00+08:00",
        data_mode="live",
        provider="jvquant",
        limit_up_count=12,
        break_board_rate=0.42,
        second_board_success_rate=0.20,
        hot_theme_count=0,
        risk_flags=["涨停家数 < 20", "炸板率 > 35%", "无热点题材"],
        positive_signals=[],
        conclusion="市场环境恶劣，不宜打板，退守观望。",
        yesterday_limitup_today_premium_pct=-2.1,
        consecutive_boards_alive_rate=0.30,
        first_to_second_promotion_rate=0.10,
        second_to_third_promotion_rate=0.05,
        max_height_today=2,
    )


# ── Candidates across all lifecycle stages ──────────────────────────────────

def _make_candidate(
    symbol: str,
    name: str,
    theme: str,
    lifecycle: str,
    theme_role: str = "leader",
    free_float_cap: float = 3_500_000_000.0,
    turnover: float = 450_000_000.0,
    avg_turnover: float = 300_000_000.0,
    shrink_ratio: float = 0.45,
    break_ct: int = 1,
    reseal_ct: int = 2,
    max_seal: float = 800_000_000.0,
    final_seal: str = "14:35:00",
    big_order_ratio: float = 0.08,
    orderbook_score: float = 75.0,
    same_theme_rising: int = 4,
) -> SecondBoardCandidate:
    return SecondBoardCandidate(
        symbol=symbol,
        name=name,
        data_mode="live",
        provider="jvquant",
        theme=theme,
        previous_limit_up_time="09:30:05",
        theme_lifecycle_stage=lifecycle,  # type: ignore[arg-type]
        theme_role=theme_role,  # type: ignore[arg-type]
        free_float_market_cap_cny=free_float_cap,
        turnover_cny=turnover,
        avg_turnover_10d_cny=avg_turnover,
        prev_day_volume_shrink_ratio=shrink_ratio,
        break_board_count=break_ct,
        reseal_count=reseal_ct,
        max_seal_amount_cny=max_seal,
        final_seal_time=final_seal,
        current_change_pct=10.0,
        five_min_speed_pct=3.2,
        big_order_net_inflow_ratio=big_order_ratio,
        orderbook_quality_score=orderbook_score,
        same_theme_rising_count=same_theme_rising,
        three_year_touch_limit_success_rate=0.60,
        three_year_sealed_next_day_gap_up_rate=0.55,
        notes=[],
    )


# 5 candidates — one per lifecycle stage
CANDIDATE_LAUNCH = _make_candidate(
    "600001", "新材科技", "固态电池",
    lifecycle="launch", theme_role="leader",
    free_float_cap=2_800_000_000.0,
    big_order_ratio=0.12, orderbook_score=82.0,
)
CANDIDATE_FERMENTING = _make_candidate(
    "300001", "智算互联", "AI算力",
    lifecycle="fermenting", theme_role="leader",
    free_float_cap=4_200_000_000.0,
    big_order_ratio=0.09, orderbook_score=78.0,
)
CANDIDATE_CLIMAX = _make_candidate(
    "000001", "海天精工", "工业母机",
    lifecycle="climax", theme_role="follower",
    free_float_cap=6_500_000_000.0,
    big_order_ratio=0.05, orderbook_score=70.0,
    break_ct=2, reseal_ct=3, max_seal=1_200_000_000.0, final_seal="14:55:00",
)
CANDIDATE_DIVERGENCE = _make_candidate(
    "002001", "东风电力", "电力改革",
    lifecycle="divergence", theme_role="follower",
    free_float_cap=15_000_000_000.0,
    big_order_ratio=-0.03, orderbook_score=55.0,
    break_ct=3, reseal_ct=1, max_seal=300_000_000.0, final_seal="10:15:00",
)
CANDIDATE_EBB = _make_candidate(
    "688001", "量子退潮", "量子计算",
    lifecycle="ebb", theme_role="follower",
    free_float_cap=8_000_000_000.0,
    big_order_ratio=-0.08, orderbook_score=40.0,
    break_ct=4, reseal_ct=0, max_seal=100_000_000.0, final_seal="unknown",
)

ALL_CANDIDATES = [
    CANDIDATE_LAUNCH,
    CANDIDATE_FERMENTING,
    CANDIDATE_CLIMAX,
    CANDIDATE_DIVERGENCE,
    CANDIDATE_EBB,
]


# ── Build per_symbol item from dossier + SKILL rules ────────────────────────

def _build_per_symbol_item(
    dossier,
    promotion_likelihood: str,
    grade: str,
) -> dict:
    """Build a well-formed per_symbol dict whose factor_analysis values
    derive from the dossier, following the SKILL.md lifecycle-downgrade rules."""
    em = dossier.market_emotion
    tp = dossier.theme_position
    fs = dossier.float_size
    ve = dossier.volume_energy
    rs = dossier.reseal_strength

    # ── Factor 1: 市场情绪 ──
    market_emotion_text = (
        f"今日涨停{em.limit_up_count}家，炸板率{em.break_board_rate:.0%}，"
        f"连板存活率{em.consecutive_boards_alive_rate:.0%}，"
        f"一进二晋级率{em.first_to_second_promotion_rate:.0%}，"
        f"热点题材{em.hot_theme_count}个，"
        f"市场情绪{em.conclusion}"
    )

    # ── Factor 2: 题材所在位置 ──
    stage_labels = {
        "launch": "启动期",
        "fermenting": "发酵期",
        "climax": "高潮期",
        "divergence": "分歧期",
        "ebb": "退潮期",
    }
    stage_cn = stage_labels.get(tp.theme_lifecycle_stage, tp.theme_lifecycle_stage)
    role_cn = {"leader": "龙头", "follower": "跟风", "unknown": "未分类"}.get(tp.theme_role, tp.theme_role)

    if tp.theme_lifecycle_stage == "divergence":
        theme_text = (
            f"题材{tp.theme}处于{stage_cn}，个股为{role_cn}。"
            f"高位分歧风险显著，依规降权：grade上限B，promotion_likelihood上限medium。"
        )
    elif tp.theme_lifecycle_stage == "ebb":
        theme_text = (
            f"题材{tp.theme}处于{stage_cn}，个股为{role_cn}。"
            f"退潮期反转风险极高，依规必须REJECT，promotion_likelihood必须low。"
        )
    elif tp.theme_lifecycle_stage == "climax":
        theme_text = (
            f"题材{tp.theme}处于{stage_cn}，个股为{role_cn}。"
            f"高潮期是分歧前最后一档，兑现风险高，promotion_likelihood"
            f"最高medium（除非量能与回封力度同时很强才可high）。"
        )
    else:
        theme_text = (
            f"题材{tp.theme}处于{stage_cn}，个股为{role_cn}，阶段有利。"
        )

    # ── Factor 3: 股本大小 ──
    cap_cn = fs.free_float_market_cap_cny / 1e8
    if fs.free_float_market_cap_cny < 5e9:
        size_verdict = "小盘弹性品种，有利于封板持续性。"
    elif fs.free_float_market_cap_cny < 10e9:
        size_verdict = "中盘股，资金拉升难度适中。"
    else:
        size_verdict = "大盘股，封板难度偏高，不利于连续晋级。"
    float_text = f"自由流通市值约{cap_cn:.0f}亿元，{size_verdict}"

    # ── Factor 4: 量能与资金 ──
    vol_ratio = ve.turnover_cny / max(ve.avg_turnover_10d_cny, 1)
    big_order_desc = "正流入" if hasattr(ve, "big_order_net_inflow_ratio") else "未知"
    volume_text = (
        f"换手金额{ve.turnover_cny / 1e8:.1f}亿元，"
        f"较十日均量{vol_ratio:.1f}倍，"
        f"昨缩量比{ve.prev_day_volume_shrink_ratio:.0%}，量能结构需关注。"
    )

    # ── Factor 5: 回封力度 ──
    reseal_text = (
        f"炸板{rs.break_board_count}次，回封{rs.reseal_count}次，"
        f"最大封单{rs.max_seal_amount_cny / 1e8:.1f}亿元，"
        f"尾盘回封时间{rs.final_seal_time}。"
    )

    # ── Natural language reason ──
    natural_reason = (
        f"该股{tp.theme}题材处于{stage_cn}，"
        f"市场今日涨停{em.limit_up_count}家，"
        f"自由流通市值约{cap_cn:.0f}亿元，"
        f"综合研判给出{grade}级，晋级概率{promotion_likelihood}。"
    )

    return {
        "symbol": dossier.symbol,
        "grade": grade,
        "promotion_likelihood": promotion_likelihood,
        "natural_language_reason": natural_reason,
        "factor_analysis": {
            "market_emotion": market_emotion_text,
            "theme_position": theme_text,
            "float_size": float_text,
            "volume_energy": volume_text,
            "reseal_strength": reseal_text,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Dossier assembly for all 5 lifecycle stages
# ═══════════════════════════════════════════════════════════════════════════

def test_a_all_lifecycle_candidates_assemble() -> None:
    """Every candidate + gate → valid PromotionDossier with all 5 factor keys."""
    gate = _make_gate_hot()
    for candidate in ALL_CANDIDATES:
        dossier = assemble_promotion_dossier(candidate, gate)
        dumped = dossier.model_dump()

        assert dossier.symbol == candidate.symbol
        assert all(key in dumped for key in REQUIRED_FACTORS), (
            f"Missing factor key in dossier for {candidate.symbol}"
        )
        # No program grade or probability fields
        banned = {"grade", "probability", "promotion_likelihood", "score"}
        assert not (set(dumped.keys()) & banned), (
            f"Program-judgment fields leaked into dossier: {set(dumped.keys()) & banned}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Hot market: 5-factor agent output passes eval
# ═══════════════════════════════════════════════════════════════════════════

def test_b_hot_market_multi_candidate_passes_eval() -> None:
    """Hot market with 5 candidates, each following SKILL downgrade rules,
    must pass agent_eval validation."""
    gate = _make_gate_hot()

    # ── Build per_symbol items respecting lifecycle downgrade rules ──
    per_symbol = []
    for candidate in ALL_CANDIDATES:
        dossier = assemble_promotion_dossier(candidate, gate)
        stage = candidate.theme_lifecycle_stage

        if stage == "launch":
            item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
        elif stage == "fermenting":
            item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
        elif stage == "climax":
            # SKILL rule: climax → promotion_likelihood max medium unless vol + reseal both strong
            # Here vol and reseal ARE strong → can give high
            item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
        elif stage == "divergence":
            # SKILL rule: divergence → grade max B, promotion_likelihood max medium
            item = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")
        elif stage == "ebb":
            # SKILL rule: ebb → grade must REJECT, promotion_likelihood must low
            item = _build_per_symbol_item(dossier, promotion_likelihood="low", grade="REJECT")
        else:
            item = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")

        per_symbol.append(item)

    agent_output = {
        "market_context": "历史回放截面，非真实行情。今日市场情绪偏暖。",
        "per_symbol": per_symbol,
        "overall_conclusion": "5只候选分别按生命周期规则评级完毕。",
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    # ── Assertions ──
    assert result["passed"] is True, (
        f"Expected pass but got: {json.dumps(result['checks'], ensure_ascii=False, indent=2)}"
    )

    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["valid_json"]["passed"] is True
    assert check_names["five_factors_present"]["passed"] is True
    assert check_names["promotion_likelihood_present"]["passed"] is True
    assert check_names["grade_present"]["passed"] is True
    assert check_names["no_direct_order_instruction"]["passed"] is True
    assert check_names["contains_non_advice_disclaimer"]["passed"] is True

    # All 5 candidates accounted for
    factor_analyses = parsed_factor_analyses(agent_output)
    assert len(factor_analyses) == 5
    likelihoods = parsed_promotion_likelihoods(agent_output)
    assert len(likelihoods) == 5
    grades = parsed_grades(agent_output)
    assert len(grades) == 5

    # Verify specific lifecycle downgrades in output
    # divergence → grade B, likelihood medium
    div_item = per_symbol[3]  # CANDIDATE_DIVERGENCE
    assert div_item["grade"] == "B"
    assert div_item["promotion_likelihood"] == "medium"
    assert "分歧" in div_item["factor_analysis"]["theme_position"]
    assert "降权" in div_item["factor_analysis"]["theme_position"]

    # ebb → grade REJECT, likelihood low
    ebb_item = per_symbol[4]  # CANDIDATE_EBB
    assert ebb_item["grade"] == "REJECT"
    assert ebb_item["promotion_likelihood"] == "low"
    assert "退潮" in ebb_item["factor_analysis"]["theme_position"]
    assert "REJECT" in ebb_item["factor_analysis"]["theme_position"]


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Cautious market: all likelihoods capped at medium
# ═══════════════════════════════════════════════════════════════════════════

def test_c_cautious_market_caps_likelihood() -> None:
    """In a cautious market, even launch-stage candidates should be capped
    at medium likelihood — the agent should exercise restraint."""
    gate = _make_gate_cautious()

    per_symbol = []
    for candidate in [CANDIDATE_LAUNCH, CANDIDATE_FERMENTING, CANDIDATE_DIVERGENCE]:
        dossier = assemble_promotion_dossier(candidate, gate)
        stage = candidate.theme_lifecycle_stage

        if stage == "launch" or stage == "fermenting":
            # Even launch/fermenting capped at medium due to cautious market
            item = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")
        elif stage == "divergence":
            item = _build_per_symbol_item(dossier, promotion_likelihood="low", grade="C")
        else:
            item = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")

        per_symbol.append(item)

    agent_output = {
        "market_context": "历史回放截面，非真实行情。今日市场偏谨慎。",
        "per_symbol": per_symbol,
        "overall_conclusion": "市场谨慎，所有候选降级观望。",
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is True, (
        f"Expected pass but got: {json.dumps(result['checks'], ensure_ascii=False, indent=2)}"
    )

    # Verify no "high" likelihood in cautious market
    likelihoods = parsed_promotion_likelihoods(agent_output)
    assert all(lh in {"medium", "low"} for lh in likelihoods), (
        f"Cautious market should not have 'high' likelihood, got: {likelihoods}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — Stale data: caps grade and likelihood mechanically
# ═══════════════════════════════════════════════════════════════════════════

def test_d_stale_data_mechanically_caps_grade_and_likelihood() -> None:
    """When freshness_status is stale, the validator must cap
    grade to ≤B and likelihood to ≤medium, regardless of factor strength."""
    gate = _make_gate_hot()
    dossier = assemble_promotion_dossier(CANDIDATE_LAUNCH, gate)

    # Try to claim "high" with stale data — should fail
    item_high = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
    agent_output = {
        "market_context": "离线合成回放，非真实行情。",
        "per_symbol": [item_high],
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="stale")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["stale_data_caps_grade"]["passed"] is False, (
        "Stale data should reject grade='A'"
    )
    assert check_names["stale_data_caps_promotion"]["passed"] is False, (
        "Stale data should reject promotion_likelihood='high'"
    )

    # Now cap correctly — should pass
    item_capped = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")
    agent_output_capped = {
        "market_context": "离线合成回放，非真实行情。",
        "per_symbol": [item_capped],
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content_capped = json.dumps(agent_output_capped, ensure_ascii=False)
    result_capped = evaluate_agent_replay_response(
        content_capped, expected_freshness_status="stale"
    )

    assert result_capped["passed"] is True, (
        f"Capped output should pass: {json.dumps(result_capped['checks'], ensure_ascii=False, indent=2)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 5 — Missing a factor fails (regression lock)
# ═══════════════════════════════════════════════════════════════════════════

def test_e_missing_factor_fails_eval() -> None:
    """Drop one factor key → five_factors_present must fail.
    This is a regression lock to prevent drift."""
    gate = _make_gate_hot()
    dossier = assemble_promotion_dossier(CANDIDATE_LAUNCH, gate)
    item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")

    # Drop float_size from factor_analysis
    incomplete_fa = {k: v for k, v in item["factor_analysis"].items() if k != "float_size"}
    incomplete_item = {**item, "factor_analysis": incomplete_fa}

    agent_output = {
        "market_context": "历史回放截面，非真实行情。",
        "per_symbol": [incomplete_item],
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["five_factors_present"]["passed"] is False, (
        "Missing float_size factor should cause five_factors_present to fail"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 6 — Per-symbol count mismatch
# ═══════════════════════════════════════════════════════════════════════════

def test_f_per_symbol_count_mismatch_fails() -> None:
    """If per_symbol has 2 items but only 1 has factor_analysis,
    the validator must detect the mismatch."""
    gate = _make_gate_hot()
    dossier_a = assemble_promotion_dossier(CANDIDATE_LAUNCH, gate)
    dossier_b = assemble_promotion_dossier(CANDIDATE_FERMENTING, gate)

    item_a = _build_per_symbol_item(dossier_a, promotion_likelihood="high", grade="A")
    # item_b deliberately has NO factor_analysis and NO promotion_likelihood
    item_b_no_factors = {
        "symbol": "300001",
        "grade": "B",
        "natural_language_reason": "只给了总结，没逐因子分析。",
        # factor_analysis and promotion_likelihood intentionally omitted
    }

    agent_output = {
        "market_context": "历史回放截面，非真实行情。",
        "per_symbol": [item_a, item_b_no_factors],
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    # promotion_likelihood count (1) != per_symbol count (2)
    assert check_names["promotion_likelihood_present"]["passed"] is False
    # factor_analysis count (1) != per_symbol count (2)
    assert check_names["five_factors_present"]["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Test 7 — End-to-end scorecard computation
# ═══════════════════════════════════════════════════════════════════════════

def test_g_full_e2e_to_scorecard() -> None:
    """Phase 2 → Phase 3 → Phase 7 complete chain for 3 candidates,
    with outcomes and scorecard computation."""
    gate = _make_gate_hot()

    candidates = [CANDIDATE_LAUNCH, CANDIDATE_FERMENTING, CANDIDATE_EBB]
    per_symbol = []

    for candidate in candidates:
        dossier = assemble_promotion_dossier(candidate, gate)
        stage = candidate.theme_lifecycle_stage

        if stage == "launch":
            item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
        elif stage == "fermenting":
            item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")
        elif stage == "ebb":
            item = _build_per_symbol_item(dossier, promotion_likelihood="low", grade="REJECT")
        else:
            item = _build_per_symbol_item(dossier, promotion_likelihood="medium", grade="B")

        per_symbol.append(item)

    agent_output = {
        "market_context": "历史回放截面，非真实行情。",
        "per_symbol": per_symbol,
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    # Validate agent output
    content = json.dumps(agent_output, ensure_ascii=False)
    eval_result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")
    assert eval_result["passed"] is True

    # Build review + outcomes
    review = AgentReview(
        run_type="daily",
        target_time="2026-06-15T09:30:00",
        symbols=["600001", "300001", "688001"],
        grades=["A", "A", "REJECT"],
        payload=agent_output,
        created_at="2026-06-15T08:00:00",
    )

    outcomes = [
        CandidateOutcomeReview(
            symbol="600001",
            trading_day="2026-06-15",
            sealed_second_board=True,
            next_day_open_pct=9.5,
            next_day_high_pct=10.0,
        ),
        CandidateOutcomeReview(
            symbol="300001",
            trading_day="2026-06-15",
            sealed_second_board=True,
            next_day_open_pct=5.0,
            next_day_high_pct=7.2,
        ),
        CandidateOutcomeReview(
            symbol="688001",
            trading_day="2026-06-15",
            sealed_second_board=False,
            next_day_open_pct=-3.1,
            next_day_high_pct=-0.5,
        ),
    ]

    sc = compute_scorecard(
        [review],
        outcomes,
        start_day="2026-06-15",
        end_day="2026-06-15",
    )

    dumped = sc.model_dump()

    assert sc.sample_size == 3
    assert sc.brier_score is not None

    # A grade → both sealed → realized_seal_rate = 1.0
    assert "A" in sc.grade_hit_rate
    assert sc.grade_hit_rate["A"]["n"] == 2.0
    assert abs(sc.grade_hit_rate["A"]["realized_seal_rate"] - 1.0) < 1e-9

    # REJECT → not sealed → realized_seal_rate = 0.0
    assert "REJECT" in sc.grade_hit_rate
    assert sc.grade_hit_rate["REJECT"]["n"] == 1.0
    assert abs(sc.grade_hit_rate["REJECT"]["realized_seal_rate"] - 0.0) < 1e-9

    # high likelihood bucket: 2 predictions, both sealed → 1.0
    assert "high" in sc.likelihood_calibration
    assert sc.likelihood_calibration["high"]["n"] == 2.0
    assert abs(sc.likelihood_calibration["high"]["realized_seal_rate"] - 1.0) < 1e-9

    # low likelihood bucket: 1 prediction, not sealed → 0.0
    assert "low" in sc.likelihood_calibration
    assert sc.likelihood_calibration["low"]["n"] == 1.0
    assert abs(sc.likelihood_calibration["low"]["realized_seal_rate"] - 0.0) < 1e-9

    # Brier: (0.8-1)^2 + (0.8-1)^2 + (0.2-0)^2 = 0.04 + 0.04 + 0.04 = 0.12 / 3 = 0.04
    assert abs(sc.brier_score - 0.04) < 1e-9, f"Expected brier≈0.04, got {sc.brier_score}"

    # No program judgment keys leaked
    _assert_no_program_judgment_keys(dumped)


# ═══════════════════════════════════════════════════════════════════════════
# Test 8 — Prohibited directive words are rejected
# ═══════════════════════════════════════════════════════════════════════════

def test_h_direct_order_words_rejected() -> None:
    """Agent output containing buy/sell directive words must be rejected."""
    gate = _make_gate_hot()
    dossier = assemble_promotion_dossier(CANDIDATE_LAUNCH, gate)
    item = _build_per_symbol_item(dossier, promotion_likelihood="high", grade="A")

    # Inject a prohibited directive into the reason
    item_bad = copy.deepcopy(item)
    item_bad["natural_language_reason"] = "建议直接买入，该股晋级概率高。"

    agent_output = {
        "market_context": "历史回放截面，非真实行情。",
        "per_symbol": [item_bad],
        "disclaimer": "仅供研究观察，不构成投资建议。",
    }

    content = json.dumps(agent_output, ensure_ascii=False)
    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["no_direct_order_instruction"]["passed"] is False, (
        f"Directive word should be flagged, detail: {check_names['no_direct_order_instruction']['detail']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _recursive_keys(obj: object) -> set[str]:
    if isinstance(obj, dict):
        keys: set[str] = set(obj.keys())
        for v in obj.values():
            keys |= _recursive_keys(v)
        return keys
    if isinstance(obj, list):
        keys: set[str] = set()
        for item in obj:
            keys |= _recursive_keys(item)
        return keys
    return set()


_PROGRAM_JUDGMENT_KEYS = {"recommendation", "advice", "program_grade", "buy", "sell", "order"}


def _assert_no_program_judgment_keys(obj: object) -> None:
    all_keys = _recursive_keys(obj)
    found = all_keys & _PROGRAM_JUDGMENT_KEYS
    assert not found, (
        f"Scorecard dict contains forbidden program-judgment keys: {found!r}."
    )
