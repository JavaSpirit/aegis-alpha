from __future__ import annotations

from aegis_alpha.measurements.tick_rule_orderflow import infer_tick_directions


def test_uptick_is_buy_downtick_is_sell_flat_is_neutral():
    trades = [
        {"price": 10.0, "volume": 100},   # 首笔无前价 → neutral
        {"price": 10.1, "volume": 200},   # 升 → buy
        {"price": 10.0, "volume": 150},   # 降 → sell
        {"price": 10.0, "volume": 120},   # 平 → neutral
    ]
    out = infer_tick_directions(trades)
    assert [t["side"] for t in out] == ["neutral", "buy", "sell", "neutral"]


def test_preserves_original_fields():
    trades = [{"price": 10.0, "volume": 100}, {"price": 10.2, "volume": 50}]
    out = infer_tick_directions(trades)
    assert out[1]["price"] == 10.2
    assert out[1]["volume"] == 50
    assert out[1]["side"] == "buy"


def test_empty_returns_empty():
    assert infer_tick_directions([]) == []
