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


def test_jvquant_adapter_get_weekly_position_from_observed_kline_shape():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeClient:
        def kline(self, code, cate="stock", fq="前复权", type="day", limit=240):
            fields = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
            if type == "week":
                rows = [
                    ["2026-06-01", "16", "18", "20", "15", "1", "1", "0", "12.50", "2", "1"],
                    ["2026-05-29", "15", "16", "17", "14", "1", "1", "0", "6.67", "1", "1"],
                    ["2026-05-22", "14", "15", "16", "13", "1", "1", "0", "7.14", "1", "1"],
                    ["2026-05-15", "13", "14", "15", "12", "1", "1", "0", "7.69", "1", "1"],
                    ["2026-05-08", "12", "13", "14", "11", "1", "1", "0", "8.33", "1", "1"],
                    ["2026-04-30", "11", "12", "13", "10", "1", "1", "0", "9.09", "1", "1"],
                    ["2026-04-25", "10", "11", "12", "9", "1", "1", "0", "10.00", "1", "1"],
                    ["2026-04-18", "10", "10", "11", "9", "1", "1", "0", "0", "0", "1"],
                ]
            else:
                rows = []
                for i in range(60):
                    day = f"2026-04-{(i % 30) + 1:02d}" if i < 30 else f"2026-05-{(i % 30) + 1:02d}"
                    close = 10 + i * 0.1
                    rows.append([day, close, close, close + 1, close - 1, "1", "1", "0", "0", "0", "1"])
                rows = list(reversed(rows))
            return {"code": 0, "data": {"fields": fields, "list": rows, "count": len(rows), "type": type}}

    adapter._client = FakeClient()
    pos = adapter.get_weekly_position("600519")
    assert pos.symbol == "600519"
    assert pos.data_mode == "live_provider"
    assert pos.trading_day == "2026-06-01"
    assert pos.weekly_high == 20.0
    assert pos.weekly_low == 9.0
    assert pos.weekly_close == 18.0
    assert pos.weeks_in_uptrend >= 6
    assert pos.ma20_above_ma60
