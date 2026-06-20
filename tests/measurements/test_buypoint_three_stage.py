from __future__ import annotations

from aegis_alpha.measurements.buypoint_state_machine import run
from aegis_alpha.models import BuyPointThresholds, MinuteReplayBar


def _bar(time: str, price: float, volume: float) -> MinuteReplayBar:
    return MinuteReplayBar(time=time, last_price=price, volume=volume)


def test_full_three_stage_fires_buy_point_alert():
    """过前高(带量) → 回踩缩量 → 重新上冲 = buy_point_alert。"""
    prev_high = 10.0
    baseline_vol = 1000.0
    thresholds = BuyPointThresholds()
    bars = [
        _bar("09:31", 10.5, 2000.0),  # 过前高, 量比 2.0 ≥ 1.5
        _bar("09:32", 10.1, 300.0),   # 回踩, 缩量
        _bar("09:33", 10.05, 200.0),  # 继续缩量探低
        _bar("09:34", 10.45, 900.0),  # 重新上冲接近 breakout
    ]
    ctx = run(bars, previous_high=prev_high, baseline_volume=baseline_vol, thresholds=thresholds)
    assert ctx.state == "buy_point_alert"
    assert ctx.triggered_at == "09:34"
    joined = " ".join(ctx.evidence)
    assert "过前高" in joined
    assert "回踩" in joined
    assert "买入预警" in joined


def test_no_volume_breakout_stays_idle():
    """过前高但量不足 → 保持 idle。"""
    bars = [_bar("09:31", 10.5, 500.0)]  # 量比 0.5 < 1.5
    ctx = run(bars, previous_high=10.0, baseline_volume=1000.0, thresholds=BuyPointThresholds())
    assert ctx.state == "idle"


def test_deep_drawdown_aborts():
    """回踩砸破位(跌幅 > 5%) → aborted。"""
    thresholds = BuyPointThresholds()
    bars = [
        _bar("09:31", 10.5, 2000.0),
        _bar("09:32", 8.0, 300.0),  # drawdown (10-8)/10 = 20% > 5%
    ]
    ctx = run(bars, previous_high=10.0, baseline_volume=1000.0, thresholds=thresholds)
    assert ctx.state == "aborted"
