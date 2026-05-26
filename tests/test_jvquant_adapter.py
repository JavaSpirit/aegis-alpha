from __future__ import annotations

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter, normalize_symbol


class FakeJvQuantClient:
    def kline(self, code: str, cate: str, fq: str, type: str, limit: int) -> dict:
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "name": "贵州茅台",
                "type": type,
                "fq": fq,
                "fields": ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"],
                "list": [
                    [
                        "2026-05-26",
                        "1285.35",
                        "1273.38",
                        "1289.89",
                        "1270.01",
                        "45932",
                        "5867830633",
                        "1.55",
                        "-0.97",
                        "-12.5",
                        "0.37",
                    ]
                ],
            },
        }

    def level_queue(self, code: str) -> dict:
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "count": 4,
                "fields": ["S2", "S1", "B1", "B2"],
                "list": [
                    {
                        "type": "S2",
                        "price": 1306.5,
                        "volume_count": 1200,
                        "queue_count": 3,
                        "queue_slice": "100,200,900",
                    },
                    {
                        "type": "S1",
                        "price": 1306.0,
                        "volume_count": 3300,
                        "queue_count": 23,
                        "queue_slice": "100,100,100",
                    },
                    {
                        "type": "B1",
                        "price": 1305.5,
                        "volume_count": 2500,
                        "queue_count": 18,
                        "queue_slice": "100,300,500",
                    },
                    {
                        "type": "B2",
                        "price": 1305.0,
                        "volume_count": 900,
                        "queue_count": 6,
                        "queue_slice": "100,200,600",
                    },
                ],
            },
        }


def test_normalize_symbol_for_jvquant() -> None:
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("000001.sz") == "000001"


def test_jvquant_realtime_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_realtime_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.name == "贵州茅台"
    assert snapshot.last_price == 1273.38
    assert snapshot.change_pct == -0.97
    assert snapshot.turnover_cny == 5867830633
    assert snapshot.bid_quality_score > 0


def test_jvquant_orderbook_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_orderbook_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.level_count == 4
    assert snapshot.best_bid_price == 1305.5
    assert snapshot.best_ask_price == 1306.0
    assert len(snapshot.bid_levels) == 2
    assert len(snapshot.ask_levels) == 2
