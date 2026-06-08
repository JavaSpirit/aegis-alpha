"""Safety and shape tests for the detect_intraday_buypoint MCP tool (Task 4.4).

These tests verify:
1. The tool returns the expected response shape (signals/count/data_mode/disclaimer).
2. No order-directive language appears anywhere in the response.
3. Results are deterministic (same inputs → identical outputs).
"""
import json


def _setup_mock_provider(monkeypatch):
    """Switch to the mock market-data provider and reset cached singletons."""
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons

    reset_singletons()


def test_detect_intraday_buypoint_returns_signals_shape(monkeypatch):
    """Result must be a dict with keys signals/count/data_mode/disclaimer.
    signals must be a list (may be empty — the mock bars may or may not fire).
    """
    _setup_mock_provider(monkeypatch)
    from aegis_alpha.mcp.server import detect_intraday_buypoint

    result = detect_intraday_buypoint("000001", previous_high=12.0)

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "signals" in result, "'signals' key missing"
    assert "count" in result, "'count' key missing"
    assert "data_mode" in result, "'data_mode' key missing"
    assert "disclaimer" in result, "'disclaimer' key missing"
    assert isinstance(result["signals"], list), "'signals' must be a list"
    assert result["count"] == len(result["signals"]), "count must equal len(signals)"


def test_detect_intraday_buypoint_no_order_language(monkeypatch):
    """The full JSON serialisation of the response must NOT contain any
    order-directive phrase.  The disclaimer contains the word 'order' in
    the phrase 'not an order instruction' — we do NOT assert that word
    absent; we assert the directive substrings absent.

    Checked:
    - Chinese directive phrases: 买入, 卖出, 下单, 全仓, 梭哈
    - No signal dict has keys: buy, sell, action, order
    """
    _setup_mock_provider(monkeypatch)
    from aegis_alpha.mcp.server import detect_intraday_buypoint

    result = detect_intraday_buypoint("000001", previous_high=12.0)
    dumped = json.dumps(result, ensure_ascii=False)

    # Chinese directive phrases must be absent anywhere in the output.
    for phrase in ("买入", "卖出", "下单", "全仓", "梭哈"):
        assert phrase not in dumped, f"Order directive phrase '{phrase}' found in output"

    # No signal dict should carry an order-related key.
    for signal in result.get("signals", []):
        for key in ("buy", "sell", "action", "order"):
            assert key not in signal, (
                f"Order-related key '{key}' found in signal dict: {signal}"
            )


def test_detect_intraday_buypoint_deterministic(monkeypatch):
    """Calling the tool twice with the same inputs must return identical results."""
    _setup_mock_provider(monkeypatch)
    from aegis_alpha.mcp.server import detect_intraday_buypoint

    first = detect_intraday_buypoint("000001", previous_high=12.0)
    second = detect_intraday_buypoint("000001", previous_high=12.0)

    assert first == second, (
        "detect_intraday_buypoint is not deterministic: "
        f"first={first}, second={second}"
    )
