from __future__ import annotations

"""
Tests for Task 3.1: agent-output contract requiring 5-factor analysis
and bucketed promotion likelihood.

These tests verify the NEW validation guards added to evaluate_agent_replay_response.
Write FIRST (RED), implement guards, then GREEN.
"""

from aegis_alpha.agent_eval import evaluate_agent_replay_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_FACTOR_ANALYSIS = {
    "market_emotion": "市场情绪偏暖，昨日涨停溢价率12%",
    "theme_position": "题材处于启动早期，龙头仍在加速",
    "float_size": "流通市值约25亿，属于小盘弹性品种",
    "volume_energy": "5日均换手率高于前期，量能持续放大",
    "reseal_strength": "昨日炸板后快速回封，封单量超3亿",
}

_BASE_VALID_RESPONSE = {
    "grade": "B",
    "natural_language_reason": "离线合成回放，规则触发但非真实行情。",
    "data_facts": ["freshness_status=fresh"],
    "rule_score": "封单衰减较高",
    "risks": ["非真实行情"],
    "trigger_conditions": {"price": [], "volume": [], "theme": [], "orderbook": []},
    "avoid_conditions": [],
    "freshness_warning": "fresh",
    "data_timestamp": "2000-01-01T09:35:00+08:00",
    "disclaimer": "仅供研究观察，不构成投资建议。",
    "promotion_likelihood": "medium",
    "factor_analysis": _VALID_FACTOR_ANALYSIS,
}


def _json_response(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Test 1: summary-only response (no factor_analysis, no promotion_likelihood)
# ---------------------------------------------------------------------------

def test_summary_only_response_fails_factor_check() -> None:
    """An agent that only gives a summary without factor_analysis /
    promotion_likelihood must FAIL validation."""
    content = _json_response({
        "grade": "B",
        "natural_language_reason": "这是离线合成回放，情绪尚可，建议观望。",
        "data_facts": ["freshness_status=fresh"],
        "risks": ["非真实行情"],
        "trigger_conditions": {"price": [], "volume": [], "theme": [], "orderbook": []},
        "avoid_conditions": [],
        "freshness_warning": "fresh",
        "data_timestamp": "2000-01-01T09:35:00+08:00",
        "disclaimer": "仅供研究观察，不构成投资建议。",
    })

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["five_factors_present"]["passed"] is False
    assert check_names["promotion_likelihood_present"]["passed"] is False


# ---------------------------------------------------------------------------
# Test 2: missing one factor key → five_factors_present False
# ---------------------------------------------------------------------------

def test_missing_one_factor_fails() -> None:
    """factor_analysis missing reseal_strength → five_factors_present False."""
    factors_incomplete = {k: v for k, v in _VALID_FACTOR_ANALYSIS.items() if k != "reseal_strength"}
    response = {**_BASE_VALID_RESPONSE, "factor_analysis": factors_incomplete}

    result = evaluate_agent_replay_response(_json_response(response), expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["five_factors_present"]["passed"] is False


# ---------------------------------------------------------------------------
# Test 3: invalid promotion_likelihood value → promotion_likelihood_present False
# ---------------------------------------------------------------------------

def test_invalid_promotion_likelihood_fails() -> None:
    """promotion_likelihood='很高' (not in {high,medium,low}) → False."""
    response = {**_BASE_VALID_RESPONSE, "promotion_likelihood": "很高"}

    result = evaluate_agent_replay_response(_json_response(response), expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["promotion_likelihood_present"]["passed"] is False


# ---------------------------------------------------------------------------
# Test 4: stale data + promotion_likelihood="high" → stale promotion check fails
# ---------------------------------------------------------------------------

def test_stale_caps_promotion_to_not_high() -> None:
    """When freshness is stale, promotion_likelihood='high' must be rejected."""
    response = {**_BASE_VALID_RESPONSE, "grade": "B", "promotion_likelihood": "high"}

    result = evaluate_agent_replay_response(_json_response(response), expected_freshness_status="stale")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["stale_data_caps_promotion"]["passed"] is False


# ---------------------------------------------------------------------------
# Test 5: complete valid response → passes
# ---------------------------------------------------------------------------

def test_complete_factor_response_passes() -> None:
    """A full valid response with all 5 factors and medium likelihood must PASS."""
    result = evaluate_agent_replay_response(
        _json_response(_BASE_VALID_RESPONSE),
        expected_freshness_status="fresh",
    )

    assert result["passed"] is True


# ---------------------------------------------------------------------------
# Test 6 (I2): per_symbol partial — one item missing factor_analysis → fail
# ---------------------------------------------------------------------------

def test_per_symbol_one_item_missing_factors_fails() -> None:
    """A per_symbol response where item 2 omits factor_analysis (and promotion_likelihood)
    must NOT slip through — five_factors_present AND promotion_likelihood_present must be False."""
    content = _json_response({
        "market_context": "历史回放截面，非真实行情。",
        "per_symbol": [
            {
                "symbol": "600519",
                "grade": "B",
                "natural_language_reason": "涨停封单稳定，题材共振明显。",
                "promotion_likelihood": "medium",
                "factor_analysis": _VALID_FACTOR_ANALYSIS,
            },
            {
                "symbol": "000001",
                "grade": "C",
                "natural_language_reason": "大单净流入低，盘口质量不佳。",
                # promotion_likelihood and factor_analysis intentionally omitted
            },
        ],
        "overall_conclusion": "600519 观望，000001 不适合。",
        "disclaimer": "仅供研究观察，不构成投资建议。",
    })

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is False
    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["five_factors_present"]["passed"] is False
    assert check_names["promotion_likelihood_present"]["passed"] is False


# ---------------------------------------------------------------------------
# Tests 7-9 (Task 3.3 — Phase 3 closeout regression locks)
# ---------------------------------------------------------------------------

def test_client_failure_summary_only_is_rejected() -> None:
    """Regression lock for client 失败2: agent picks 6 candidates but gives ONLY an
    overall_conclusion summary with no per-symbol factor_analysis or promotion_likelihood.
    This is the exact failure shape the client reported — the validator MUST reject it.
    """
    # Realistic summary-only agent response: 6 candidates, no per-symbol factor walk
    content = _json_response({
        "market_context": "今日市场整体偏暖，涨停42家，炸板率18%，连板存活率62%。",
        "per_symbol": [
            {
                "symbol": "600519",
                "grade": "B",
                "natural_language_reason": "贵州茅台估值偏高，短期动能有限。",
                # 故意省略 factor_analysis 与 promotion_likelihood —— 模拟只给总结的失败模式
            },
            {
                "symbol": "000858",
                "grade": "B",
                "natural_language_reason": "五粮液与茅台同向，情绪传导预期一般。",
            },
            {
                "symbol": "300750",
                "grade": "C",
                "natural_language_reason": "宁德时代量能收缩，关注度下降。",
            },
            {
                "symbol": "002594",
                "grade": "C",
                "natural_language_reason": "比亚迪板块整体压力较大，观望为主。",
            },
            {
                "symbol": "601012",
                "grade": "B",
                "natural_language_reason": "隆基绿能受政策利好，但短期已有较大涨幅。",
            },
            {
                "symbol": "688599",
                "grade": "C",
                "natural_language_reason": "天合光能前期高位，近期分歧明显。",
            },
        ],
        # 只有整体总结，没有逐项因子分析 —— 这是 失败2 的核心问题
        "overall_conclusion": (
            "综合来看，今日6只候选股情绪尚可，但缺乏明确主驱动，建议以B/C观望为主，"
            "不宜追高，静待量能与板块轮动信号。"
        ),
        "disclaimer": "仅供研究观察，不构成投资建议。",
    })

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    # The whole response must fail
    assert result["passed"] is False

    check_names = {c["name"]: c for c in result["checks"]}
    # BOTH factor and likelihood checks must be False — no per-symbol walk was done
    assert check_names["five_factors_present"]["passed"] is False, (
        "Expected five_factors_present to be False: no per-symbol factor_analysis provided"
    )
    assert check_names["promotion_likelihood_present"]["passed"] is False, (
        "Expected promotion_likelihood_present to be False: no per-symbol promotion_likelihood provided"
    )


def test_client_failure_late_stage_high_likelihood_when_stale_is_capped() -> None:
    """Regression lock for the freshness-cap side of 失败2/失败3:
    a complete factor response with promotion_likelihood='high' but
    expected_freshness_status='stale' must fail the stale_data_caps_promotion check.

    Note: the late-stage-theme downweight (divergence/ebb ceilings) is a SKILL.md
    INSTRUCTION to the LLM, not a mechanical validator rule.  The validator's job
    here is narrower: enforce that stale data cannot yield a 'high' likelihood.
    """
    response = {
        **_BASE_VALID_RESPONSE,
        "promotion_likelihood": "high",
        # factor_analysis is complete (inherited from _BASE_VALID_RESPONSE)
    }

    result = evaluate_agent_replay_response(
        _json_response(response),
        expected_freshness_status="stale",
    )

    assert result["passed"] is False

    check_names = {c["name"]: c for c in result["checks"]}
    # The stale freshness cap must be enforced mechanically
    assert check_names["stale_data_caps_promotion"]["passed"] is False, (
        "Expected stale_data_caps_promotion to be False: stale data cannot have promotion_likelihood='high'"
    )


def test_complete_5factor_response_with_likelihood_passes() -> None:
    """Regression lock proving a correct, complete 5-factor response passes validation.

    Two candidates, each with all 5 factor_analysis keys (non-empty Chinese text),
    a valid bucketed promotion_likelihood, agent grade, and natural_language_reason.
    Top-level disclaimer + offline keyword + expected_freshness_status='fresh'.
    """
    content = _json_response({
        "market_context": "历史回放截面，非真实行情。今日涨停45家，炸板率15%。",
        "per_symbol": [
            {
                "symbol": "600519",
                "grade": "A",
                "natural_language_reason": (
                    "市场情绪整体向好，题材处于启动期，股本偏小弹性强，"
                    "量能持续放大且大单净流入为正，回封速度快封单厚实，综合评为A。"
                ),
                "promotion_likelihood": "high",
                "factor_analysis": {
                    "market_emotion": "涨停45家，炸板率15%，连板存活率68%，市场情绪偏强，支撑二板进攻。",
                    "theme_position": (
                        "题材处于发酵阶段（fermenting），龙头仍在加速，尚未进入高潮期，风险可控。"
                    ),
                    "float_size": "流通市值约22亿，属于小盘弹性品种，有利于封板持续性。",
                    "volume_energy": (
                        "5日均换手率高于前期基准，大单净流入比例+8.3%，盘口质量评分0.82，量能持续放大。"
                    ),
                    "reseal_strength": (
                        "昨日炸板1次后5分钟内快速回封，最大封单额3.2亿，封成比89%，意愿强烈。"
                    ),
                },
            },
            {
                "symbol": "000001",
                "grade": "B",
                "natural_language_reason": (
                    "题材处于分歧阶段，封板持续性存疑，大单净流入偏低，"
                    "虽然市场情绪尚可但单只股本偏大，综合给B观望。"
                ),
                "promotion_likelihood": "medium",
                "factor_analysis": {
                    "market_emotion": "同上市场情绪背景，45家涨停，整体支撑有限。",
                    "theme_position": (
                        "题材处于分歧阶段（divergence），高位风险偏高，依规降权，grade上限为B。"
                    ),
                    "float_size": "流通市值约850亿，大盘股封板难度高，不利于连续晋级。",
                    "volume_energy": (
                        "换手率近两日收缩，大单净流入比例-1.2%，盘口质量评分0.55，量能偏弱。"
                    ),
                    "reseal_strength": "未有炸板回封记录，封单额约0.8亿，封成比偏低，回封意愿一般。",
                },
            },
        ],
        "overall_conclusion": "600519 A级候选，000001 B级观望。",
        "disclaimer": "仅供研究观察，不构成投资建议。",
    })

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is True, (
        f"Expected full 5-factor response to pass, but got checks: {result['checks']}"
    )

    check_names = {c["name"]: c for c in result["checks"]}
    assert check_names["five_factors_present"]["passed"] is True
    assert check_names["promotion_likelihood_present"]["passed"] is True
    assert check_names["grade_present"]["passed"] is True
