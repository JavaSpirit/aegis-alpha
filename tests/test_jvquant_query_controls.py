from __future__ import annotations

import pytest

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter


class CountingClient:
    def __init__(self) -> None:
        self.calls = 0

    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
        self.calls += 1
        return {"code": 0, "data": {"fields": ["代码"], "list": [["600000"]]}}


def test_jvquant_query_uses_ttl_cache(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALPHA_JVQUANT_CACHE_TTL_SECONDS", "30")
    adapter = JvQuantMarketDataAdapter(token="fake")
    client = CountingClient()
    adapter._client = client

    assert adapter._query("今日涨停", sort_key="涨跌幅") == adapter._query("今日涨停", sort_key="涨跌幅")
    assert client.calls == 1


def test_jvquant_query_timeout(monkeypatch) -> None:
    class SlowClient:
        def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
            import time

            time.sleep(0.03)
            return {}

    monkeypatch.setenv("AEGIS_ALPHA_JVQUANT_QUERY_TIMEOUT_SECONDS", "0.001")
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = SlowClient()

    with pytest.raises(TimeoutError):
        adapter._query("今日涨停")
