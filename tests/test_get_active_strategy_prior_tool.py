"""TDD: get_active_strategy_prior MCP tool — read-only guidance, no mutation, no filter.

RED phase: run before implementing the tool; all tests should FAIL.
GREEN phase: run after implementing the tool; all tests should PASS.
"""
from __future__ import annotations


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
# Happy path: active prior loaded from real config
# ---------------------------------------------------------------------------
def test_get_active_strategy_prior_happy_path(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_active_strategy_prior

    reset_singletons()
    result = get_active_strategy_prior()

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("prior_id") == "client_10pt", f"Expected 'client_10pt', got {result.get('prior_id')!r}"
    assert result.get("is_active") is True, f"Expected is_active True, got {result.get('is_active')!r}"

    thresholds = result.get("thresholds")
    assert isinstance(thresholds, list) and len(thresholds) > 0, (
        f"Expected non-empty thresholds list, got {thresholds!r}"
    )

    guidance_notes = result.get("guidance_notes")
    assert isinstance(guidance_notes, list) and len(guidance_notes) > 0, (
        f"Expected non-empty guidance_notes list, got {guidance_notes!r}"
    )

    caixin = result.get("caixin_alignment", "")
    assert caixin.startswith("placeholder"), (
        f"Expected caixin_alignment to start with 'placeholder', got {caixin!r}"
    )


# ---------------------------------------------------------------------------
# Read-only / no-filter contract: banned keys, override_policy, disclaimer
# ---------------------------------------------------------------------------
def test_get_active_strategy_prior_no_filter_contract(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_active_strategy_prior

    reset_singletons()
    result = get_active_strategy_prior()

    # Must NOT contain any filter/grade/score/probability keys anywhere
    banned_fields = {"passed", "meets_threshold", "reject", "filter", "grade", "score", "probability"}
    all_keys = _all_keys(result)
    found_banned = banned_fields & all_keys
    assert not found_banned, f"Banned filter/grade fields found in prior result: {found_banned}"

    # override_policy must contain the Chinese phrase "事实为准"
    override_policy = result.get("override_policy", "")
    assert "事实为准" in override_policy, (
        f"override_policy must contain '事实为准', got: {override_policy!r}"
    )

    # disclaimer must signal "not a program filter"
    disclaimer = result.get("disclaimer", "")
    assert "not a program filter" in disclaimer, (
        f"disclaimer must contain 'not a program filter', got: {disclaimer!r}"
    )


# ---------------------------------------------------------------------------
# No-active path: monkeypatch loader to return None → tool returns unavailable
# ---------------------------------------------------------------------------
def test_get_active_strategy_prior_no_active(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_active_strategy_prior

    reset_singletons()

    # Patch the loader at the module level where it's defined
    monkeypatch.setattr(
        "aegis_alpha.strategy_priors.load_active_strategy_prior",
        lambda path=None: None,
    )

    result = get_active_strategy_prior()

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("data_mode") == "unavailable", (
        f"Expected data_mode 'unavailable', got {result.get('data_mode')!r}"
    )
    assert "error" in result, "Expected 'error' key in unavailable result"
