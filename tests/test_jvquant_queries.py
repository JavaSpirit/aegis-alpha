from __future__ import annotations

from aegis_alpha.adapters.jvquant.queries import JvQuantQueryClient


class CountingClient:
    def __init__(self) -> None:
        self.calls = 0

    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
        self.calls += 1
        return {"code": 0, "data": {"fields": ["代码"], "list": [["600000"]]}}


def test_jvquant_query_client_caches_by_query_and_sort_key() -> None:
    wrapper = JvQuantQueryClient(cache_ttl_seconds=30, query_rate_per_second=10, query_burst=10)
    client = CountingClient()

    assert wrapper.query(client, "今日涨停", "涨跌幅") == wrapper.query(client, "今日涨停", "涨跌幅")
    assert client.calls == 1

    wrapper.query(client, "今日涨停", "成交额")
    assert client.calls == 2
