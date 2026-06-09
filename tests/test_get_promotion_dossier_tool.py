"""TDD: get_promotion_dossier MCP tool — facts-only dossier, no score, no order.

RED phase: run before implementing the tool; all tests should FAIL.
GREEN phase: run after implementing the tool; all tests should PASS.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helper: recursive key extractor (mirrors test_promotion_dossier_model.py)
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
# Happy path: valid symbol present in the mock adapter pool
# ---------------------------------------------------------------------------
def test_get_promotion_dossier_happy_path(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_promotion_dossier

    reset_singletons()
    # "002230.SZ" is a known mock candidate (科大讯飞)
    result = get_promotion_dossier("002230.SZ")

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    # Must contain all 5 factor keys
    required_factors = {"market_emotion", "theme_position", "float_size", "volume_energy", "reseal_strength"}
    for key in required_factors:
        assert key in result, f"Missing required factor key: {key}"

    # Must NOT contain any grading/probability fields anywhere in the structure
    banned_fields = {
        "grade",
        "probability",
        "score",
        "promotion_likelihood",
        "estimated_seal_probability",
    }
    all_keys = _all_keys(result)
    found_banned = banned_fields & all_keys
    assert not found_banned, f"Banned grading/probability fields found in dossier: {found_banned}"


# ---------------------------------------------------------------------------
# Not-found path: bogus symbol returns unavailable sentinel
# ---------------------------------------------------------------------------
def test_get_promotion_dossier_not_found(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_promotion_dossier

    reset_singletons()
    result = get_promotion_dossier("ZZZZZZ")

    assert isinstance(result, dict)
    assert result.get("data_mode") == "unavailable"
    assert "error" in result


# ---------------------------------------------------------------------------
# No-order guard: disclaimer must not contain imperative order words
# ---------------------------------------------------------------------------
def test_get_promotion_dossier_disclaimer_no_order_words(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_promotion_dossier

    reset_singletons()
    result = get_promotion_dossier("002230.SZ")

    # Disclaimer must be present and signal facts-only intent
    assert "disclaimer" in result, "Missing 'disclaimer' in dossier result"
    disclaimer = result["disclaimer"]
    assert "Not a buy/sell/order" in disclaimer, (
        f"Disclaimer does not contain 'Not a buy/sell/order': {disclaimer!r}"
    )
