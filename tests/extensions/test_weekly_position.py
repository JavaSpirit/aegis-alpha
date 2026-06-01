from aegis_alpha.models import WeeklyPosition
from aegis_alpha.extensions.weekly_position import (
    compute_weekly_health_score,
)


def _pos(position_pct=0.5, weeks_uptrend=2, ma_above=True):
    return WeeklyPosition(
        symbol="X",
        trading_day="2026-06-01",
        weekly_high=110.0,
        weekly_low=90.0,
        weekly_close=100.0,
        position_pct=position_pct,
        weeks_in_uptrend=weeks_uptrend,
        ma20_above_ma60=ma_above,
    )


def test_weekly_health_score_high_when_strong_position_and_uptrend():
    score = compute_weekly_health_score(_pos(0.85, weeks_uptrend=4, ma_above=True))
    assert score >= 75.0


def test_weekly_health_score_low_when_weak_position_no_uptrend_ma_below():
    score = compute_weekly_health_score(_pos(0.05, weeks_uptrend=0, ma_above=False))
    assert score <= 25.0


def test_weekly_health_score_neutral_when_mid():
    score = compute_weekly_health_score(_pos(0.5, weeks_uptrend=1, ma_above=True))
    assert 40.0 <= score <= 60.0


def test_weekly_health_score_clamped_to_0_100():
    extreme = WeeklyPosition(
        symbol="X", trading_day="2026-06-01",
        weekly_high=200.0, weekly_low=50.0, weekly_close=200.0,
        position_pct=1.0, weeks_in_uptrend=20, ma20_above_ma60=True,
    )
    score = compute_weekly_health_score(extreme)
    assert 0.0 <= score <= 100.0


def test_mock_adapter_returns_weekly_position():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pos = adapter.get_weekly_position("600519")
    assert isinstance(pos, WeeklyPosition)
    assert pos.symbol == "600519"
    assert pos.data_mode == "mock"
    assert 0.0 <= pos.position_pct <= 1.0


def test_jvquant_adapter_get_weekly_position_returns_placeholder():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    pos = adapter.get_weekly_position("600519")
    assert pos.symbol == "600519"
    assert pos.data_mode == "placeholder"
