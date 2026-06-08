from aegis_alpha.models import BuyPointThresholds, IntradayBuyPointSignal


def test_thresholds_have_injectable_defaults():
    t = BuyPointThresholds()
    assert t.breakout_volume_ratio_min == 1.5
    assert t.pullback_volume_shrink_max == 0.7
    assert t.resurge_strength_min == 0.5
    assert t.pullback_max_drawdown_pct == 5.0


def test_thresholds_are_overridable():
    t = BuyPointThresholds(breakout_volume_ratio_min=2.0)
    assert t.breakout_volume_ratio_min == 2.0


def test_signal_is_facts_only_no_order_field():
    fields = set(IntradayBuyPointSignal.model_fields)
    # measured-fact fields present
    for f in ("state", "triggered_at", "breakout_volume_ratio",
              "pullback_volume_shrink_ratio", "resurge_strength",
              "same_theme_co_pumping_count", "evidence"):
        assert f in fields, f"missing {f}"
    # NO buy/sell/order field
    for forbidden in ("buy", "sell", "order", "action", "position"):
        assert forbidden not in fields


def test_signal_default_state_is_idle():
    s = IntradayBuyPointSignal(symbol="000001", trading_day="2026-06-08")
    assert s.state == "idle"
    assert s.triggered_at == ""
