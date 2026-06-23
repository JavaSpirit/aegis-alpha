from __future__ import annotations

from aegis_alpha.mcp import server
from aegis_alpha.models import MarketEvent, SignalSnapshot


def _store(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    return store


def _event(event_id: str, event_type: str, symbol: str, score: float, theme: str = "AI算力", fresh="fresh"):
    return MarketEvent(
        event_id=event_id, event_type=event_type, symbol=symbol, theme=theme,
        score=score, received_at="2026-06-23T09:40:00+08:00", freshness_status=fresh,
    )


def _snapshot(symbol: str, fresh="fresh"):
    return SignalSnapshot(
        symbol=symbol, data_timestamp="2026-06-23T09:40:00+08:00",
        provider_timestamp="2026-06-23T09:40:00+08:00",
        received_at="2026-06-23T09:40:00+08:00", freshness_status=fresh,
        change_pct=8.8, speed_5m_pct=2.1,
    )


# --- get_realtime_symbol_context ---

def test_symbol_context_empty_db(monkeypatch, tmp_path):
    _store(monkeypatch, tmp_path)
    res = server.get_realtime_symbol_context("002491")
    assert res["data_mode"] == "ok"
    assert res["snapshot"] is None
    assert res["recent_event_count"] == 0
    assert res["freshness"] == "no_data"
    assert any("结构化快照" in g for g in res["data_gaps"])


def test_symbol_context_requires_symbol(monkeypatch, tmp_path):
    _store(monkeypatch, tmp_path)
    res = server.get_realtime_symbol_context("")
    assert res["data_mode"] == "unavailable"


def test_symbol_context_with_data(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    store.save_signal_snapshot(_snapshot("002491"))
    store.save_market_events([
        _event("e1", "APPROACHING_LIMIT_UP", "002491", 78.0),
        _event("e2", "BIG_ORDER_INFLOW_SPIKE", "300475", 60.0),  # different symbol
    ])
    res = server.get_realtime_symbol_context("002491")
    assert res["data_mode"] == "ok"
    assert res["snapshot"] is not None
    assert res["snapshot"]["symbol"] == "002491"
    assert res["recent_event_count"] == 1  # only 002491's event
    assert res["recent_events"][0]["event_id"] == "e1"
    assert res["freshness"] == "has_fresh"


def test_symbol_context_stale_only(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    store.save_market_events([_event("e1", "APPROACHING_LIMIT_UP", "002491", 50.0, fresh="stale")])
    res = server.get_realtime_symbol_context("002491")
    assert res["freshness"] == "all_stale"


# --- get_intraday_market_context ---

def test_market_context_empty_db(monkeypatch, tmp_path):
    _store(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "status_payload", lambda: {"state": "WAITING", "subscribed": []})
    res = server.get_intraday_market_context()
    assert res["data_mode"] == "ok"
    assert res["total_recent_events"] == 0
    assert res["event_count_by_type"] == {}
    assert any("无结构化事件" in g for g in res["data_gaps"])
    assert any("runner 状态" in g for g in res["data_gaps"])


def test_market_context_with_events(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        server, "status_payload",
        lambda: {"state": "RUNNING", "subscribed": ["002491", "300475", "600519"]},
    )
    store.save_market_events([
        _event("e1", "APPROACHING_LIMIT_UP", "002491", 90.0),
        _event("e2", "APPROACHING_LIMIT_UP", "300475", 70.0),
        _event("e3", "BIG_ORDER_INFLOW_SPIKE", "600519", 55.0),
    ])
    res = server.get_intraday_market_context()
    assert res["data_mode"] == "ok"
    assert res["runner_state"] == "RUNNING"
    assert res["monitored_symbol_count"] == 3
    assert res["event_count_by_type"]["APPROACHING_LIMIT_UP"] == 2
    assert res["total_recent_events"] == 3
    # strongest first
    assert res["strongest_events"][0]["event_id"] == "e1"
    assert len(res["approaching_limit_up"]) == 2
    assert res["freshness"] == "has_fresh"


def test_market_context_runner_status_failure_soft(monkeypatch, tmp_path):
    _store(monkeypatch, tmp_path)
    def _boom():
        raise RuntimeError("status file gone")
    monkeypatch.setattr(server, "status_payload", _boom)
    res = server.get_intraday_market_context()
    assert res["data_mode"] == "ok"
    assert res["runner_state"] == "STOPPED"
