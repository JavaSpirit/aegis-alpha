from __future__ import annotations

from aegis_alpha.mcp import server


def test_get_tick_rule_orderflow_proxy_tool_exists():
    assert hasattr(server, "get_tick_rule_orderflow_proxy")


def test_orderflow_proxy_marks_non_truth(monkeypatch):
    class _FakeAdapter:
        def sample_realtime_large_trade_proxy(self, symbol, threshold_cny=3_000_000.0,
                                              window_start="", window_end=""):
            return {
                "symbol": symbol,
                "sample_available": True,
                "stats": {
                    "sample_trades": [
                        {"time": "09:41", "amount_cny": 2_000_000.0, "price": 20.0, "volume": 100_000.0},
                        {"time": "09:42", "amount_cny": 2_020_000.0, "price": 20.2, "volume": 100_000.0},
                    ],
                },
            }
    monkeypatch.setattr(server, "get_market_data_adapter", lambda: _FakeAdapter())
    result = server.get_tick_rule_orderflow_proxy("002230", big_trade_threshold_cny=1_000_000.0)
    assert result["is_exchange_truth"] is False
    assert result["method"] == "tick_rule"
    assert "accuracy_caveat" in result
    assert result["symbol"] == "002230"
    assert result["upstream_sample_available"] is True
    assert result["data_mode"] == "computed"


def test_orderflow_proxy_unavailable_when_no_sample(monkeypatch):
    class _EmptyAdapter:
        def sample_realtime_large_trade_proxy(self, symbol, threshold_cny=3_000_000.0,
                                              window_start="", window_end=""):
            return {"symbol": symbol, "sample_available": False, "stats": {"sample_trades": []}}
    monkeypatch.setattr(server, "get_market_data_adapter", lambda: _EmptyAdapter())
    result = server.get_tick_rule_orderflow_proxy("002230")
    assert result["data_mode"] == "unavailable"
    assert result["is_exchange_truth"] is False
    assert result["upstream_sample_available"] is False
