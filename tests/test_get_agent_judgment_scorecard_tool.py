"""TDD: get_agent_judgment_scorecard MCP tool — read-only calibration metrics.

Task 7.3: Surfaces the agent's calibration scorecard (Brier score, likelihood
calibration, grade hit-rate). No buy/sell/order; no auto-applied changes.

RED phase: run before implementing the tool; all tests should FAIL.
GREEN phase: run after implementing the tool; all tests should PASS.
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Helper: recursive key extractor (mirrors test_get_promotion_dossier_tool.py)
# ---------------------------------------------------------------------------
def _all_keys(obj: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


# ---------------------------------------------------------------------------
# Seeded happy path: one AgentReview + one matching CandidateOutcomeReview
# ---------------------------------------------------------------------------
def test_get_agent_judgment_scorecard_seeded_happy_path(monkeypatch, tmp_path):
    """Seed one AgentReview with per_symbol grade+likelihood and one matching
    CandidateOutcomeReview (sealed_second_board=True).  Call the tool over a
    window that includes those records and assert:
    - sample_size >= 1
    - brier_score is not None
    - required scorecard keys all present
    """
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")

    from aegis_alpha.storage import AegisAlphaStore
    from aegis_alpha.models import AgentReview, CandidateOutcomeReview
    import aegis_alpha.mcp.dependencies as dep

    # Create a fresh temp store and inject it as the singleton
    store = AegisAlphaStore(str(tmp_path / "scorecard_test.db"))
    dep.reset_singletons()
    monkeypatch.setattr(dep, "_store", store)

    # Seed an AgentReview whose target_time falls within 2026-06-01..2026-06-30
    review = AgentReview(
        run_type="historical_snapshot_eval",
        target_time="2026-06-10T10:00:00+08:00",
        symbols=["600519"],
        provider="deepseek",
        model="deepseek-v4-pro",
        passed=True,
        grades=["A"],
        summary={},
        payload={
            "per_symbol": [
                {
                    "symbol": "600519",
                    "grade": "A",
                    "promotion_likelihood": "high",
                }
            ]
        },
    )
    store.save_agent_review(review)

    # Seed a matching CandidateOutcomeReview for the same symbol on the same trading day
    outcome = CandidateOutcomeReview(
        symbol="600519",
        trading_day="2026-06-10",
        sealed_second_board=True,
    )
    store.save_review_outcome(outcome)

    # Import and call the tool (should exist after GREEN phase)
    from aegis_alpha.mcp.server import get_agent_judgment_scorecard

    result = get_agent_judgment_scorecard("2026-06-01", "2026-06-30")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("sample_size", 0) >= 1, (
        f"Expected sample_size >= 1, got {result.get('sample_size')!r}"
    )
    assert result.get("brier_score") is not None, (
        f"Expected non-None brier_score, got {result.get('brier_score')!r}"
    )

    # All five required scorecard keys must be present
    for key in ("likelihood_calibration", "grade_hit_rate", "rows", "sample_size", "disclaimer"):
        assert key in result, f"Missing required scorecard key: '{key}'"


# ---------------------------------------------------------------------------
# Empty window: no matching reviews → sample_size == 0, brier_score is None
# ---------------------------------------------------------------------------
def test_get_agent_judgment_scorecard_empty_window(monkeypatch, tmp_path):
    """An empty date window (no seeded data) must return sample_size=0 and
    brier_score=None without crashing."""
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")

    from aegis_alpha.storage import AegisAlphaStore
    import aegis_alpha.mcp.dependencies as dep

    store = AegisAlphaStore(str(tmp_path / "empty_test.db"))
    dep.reset_singletons()
    monkeypatch.setattr(dep, "_store", store)

    from aegis_alpha.mcp.server import get_agent_judgment_scorecard

    result = get_agent_judgment_scorecard("2025-01-01", "2025-01-31")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("sample_size") == 0, (
        f"Expected sample_size == 0, got {result.get('sample_size')!r}"
    )
    assert result.get("brier_score") is None, (
        f"Expected brier_score None, got {result.get('brier_score')!r}"
    )
    # No crash — tool must not raise
    assert "data_mode" not in result or result.get("data_mode") != "unavailable", (
        "Empty window should return a scorecard, not unavailable"
    )


# ---------------------------------------------------------------------------
# Missing start_day: must return data_mode='unavailable' with error
# ---------------------------------------------------------------------------
def test_get_agent_judgment_scorecard_missing_start_day(monkeypatch):
    """Calling with an empty start_day must return {data_mode: 'unavailable', error: ...}."""
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons

    reset_singletons()

    from aegis_alpha.mcp.server import get_agent_judgment_scorecard

    result = get_agent_judgment_scorecard("")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("data_mode") == "unavailable", (
        f"Expected data_mode 'unavailable', got {result.get('data_mode')!r}"
    )
    assert "error" in result, "Expected 'error' key in missing-start_day result"


# ---------------------------------------------------------------------------
# No-order/no-grade contract: banned keys must not appear anywhere in output
# ---------------------------------------------------------------------------
def test_get_agent_judgment_scorecard_no_order_contract(monkeypatch, tmp_path):
    """The returned dict (recursive scan) must contain none of the banned keys:
    buy, sell, order, program_grade, recommendation.
    The disclaimer must contain the phrase 'not a buy/sell/order'.
    """
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")

    from aegis_alpha.storage import AegisAlphaStore
    from aegis_alpha.models import AgentReview, CandidateOutcomeReview
    import aegis_alpha.mcp.dependencies as dep

    store = AegisAlphaStore(str(tmp_path / "contract_test.db"))
    dep.reset_singletons()
    monkeypatch.setattr(dep, "_store", store)

    # Seed minimal data so the tool returns a real scorecard
    review = AgentReview(
        run_type="historical_snapshot_eval",
        target_time="2026-06-15T10:00:00+08:00",
        symbols=["000001"],
        provider="deepseek",
        model="deepseek-v4-pro",
        passed=False,
        grades=["B"],
        summary={},
        payload={
            "per_symbol": [
                {
                    "symbol": "000001",
                    "grade": "B",
                    "promotion_likelihood": "medium",
                }
            ]
        },
    )
    store.save_agent_review(review)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="000001",
            trading_day="2026-06-15",
            sealed_second_board=False,
        )
    )

    from aegis_alpha.mcp.server import get_agent_judgment_scorecard

    result = get_agent_judgment_scorecard("2026-06-01", "2026-06-30")

    # Recursive key scan — none of the banned keys should appear
    banned_keys = {"buy", "sell", "order", "program_grade", "recommendation"}
    found_banned = banned_keys & _all_keys(result)
    assert not found_banned, (
        f"Banned order/grade keys found in scorecard result: {found_banned}"
    )

    # disclaimer must explicitly signal "not a buy/sell/order"
    disclaimer = result.get("disclaimer", "")
    assert "not a buy/sell/order" in disclaimer, (
        f"disclaimer must contain 'not a buy/sell/order', got: {disclaimer!r}"
    )

    # Also check JSON serialisation for order-directive text
    dumped = json.dumps(result, ensure_ascii=False)
    for phrase in ("卖出", "下单", "全仓", "梭哈"):
        assert phrase not in dumped, (
            f"Order-directive phrase '{phrase}' found in scorecard output"
        )
