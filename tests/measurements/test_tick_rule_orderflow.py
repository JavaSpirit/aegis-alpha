from __future__ import annotations

from aegis_alpha.measurements.tick_rule_orderflow import infer_tick_directions
from aegis_alpha.measurements.tick_rule_orderflow import tick_rule_big_buy_ratio_proxy


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


def test_big_buy_ratio_proxy_basic():
    trades = [
        {"price": 10.0, "volume": 100000},   # neutral, 100万
        {"price": 10.1, "volume": 100000},   # buy, 101万 ≥ 阈值
        {"price": 10.2, "volume": 100000},   # buy, 102万
        {"price": 10.1, "volume": 100000},   # sell, 101万
    ]
    result = tick_rule_big_buy_ratio_proxy(
        trades, big_trade_threshold_cny=1_000_000.0, limit_up_price=0.0,
    )
    assert result["is_exchange_truth"] is False
    assert result["method"] == "tick_rule"
    assert 0.0 < result["tick_rule_big_buy_ratio_proxy"] <= 1.0
    assert result["sealing_distortion_warning"] is False
    assert "accuracy_caveat" in result
    assert result["data_mode"] == "computed"


def test_sealing_distortion_warning_near_limit_up():
    trades = [
        {"price": 10.99, "volume": 200000},
        {"price": 11.0, "volume": 200000},   # 触及涨停价
    ]
    result = tick_rule_big_buy_ratio_proxy(
        trades, big_trade_threshold_cny=1_000_000.0, limit_up_price=11.0,
    )
    assert result["sealing_distortion_warning"] is True


def test_empty_trades_unavailable():
    result = tick_rule_big_buy_ratio_proxy([], big_trade_threshold_cny=1_000_000.0, limit_up_price=0.0)
    assert result["data_mode"] == "unavailable"
    assert result["is_exchange_truth"] is False
    assert result["sealing_distortion_warning"] is False
