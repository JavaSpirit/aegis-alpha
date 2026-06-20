from __future__ import annotations

import json
from aegis_alpha.storage import AegisAlphaStore
from aegis_alpha.mcp import server as srv


def test_trigger_validation_joins_audit_and_facts(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)

    picks = json.dumps([{"symbol": "002491", "rank": 1, "relative_reason": "胜过X"}])
    srv.record_selection_audit("2026-06-18", picks)

    monkeypatch.setattr(srv, "_validation_intraday_trigger",
                        lambda sym, as_of, target, ws, we: {"triggered": True, "trigger_time": "09:33", "data_mode": "ok"})
    monkeypatch.setattr(srv, "_validation_next_day_outcome",
                        lambda sym, target: {"sealed_second_board": True, "next_day_open_pct": 3.2, "data_mode": "ok"})

    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")
    assert res["data_mode"] == "ok"
    assert res["total"] == 1
    assert res["per_pick"][0]["symbol"] == "002491"
    assert res["per_pick"][0]["triggered"] is True
    assert res["triggered_count"] == 1
    assert res["trigger_rate"] == 1.0
    assert "confidence_label" in res


def test_trigger_validation_no_audit_unavailable(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    res = srv.get_selection_trigger_validation("2099-01-01", "2099-01-02")
    assert res["data_mode"] == "unavailable"


def test_trigger_validation_degrades_when_upstream_fails(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    picks = json.dumps([{"symbol": "002491", "rank": 1}])
    srv.record_selection_audit("2026-06-18", picks)
    # upstream helpers degrade (return None triggered / unavailable) — must not crash
    monkeypatch.setattr(srv, "_validation_intraday_trigger",
                        lambda *a: {"triggered": None, "trigger_time": "", "data_mode": "unavailable"})
    monkeypatch.setattr(srv, "_validation_next_day_outcome",
                        lambda *a: {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "unavailable"})
    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")
    assert res["data_mode"] == "ok"
    assert res["triggered_count"] == 0
    assert res["per_pick"][0]["trigger_data_mode"] == "unavailable"
