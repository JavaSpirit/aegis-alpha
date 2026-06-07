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
    import copy
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
