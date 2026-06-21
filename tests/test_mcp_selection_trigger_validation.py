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


def test_trigger_validation_propagates_upstream_unavailable(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    srv.record_selection_audit("2026-06-18", json.dumps([{"symbol": "002491", "rank": 1}]))
    monkeypatch.setattr(srv, "get_strategy_decision_packet", lambda *a, **k: {"data_mode": "unavailable"})
    monkeypatch.setattr(srv, "get_second_board_next_day_outcomes", lambda *a, **k: {"data_mode": "unavailable"})
    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")
    assert res["data_mode"] == "ok"  # tool itself succeeded
    assert res["per_pick"][0]["trigger_data_mode"] == "unavailable"
    assert res["per_pick"][0]["outcome_data_mode"] == "unavailable"
    assert res["triggered_count"] == 0


def test_trigger_validation_does_not_count_opening_cross_as_buy_point(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    srv.record_selection_audit("2026-06-18", json.dumps([{"symbol": "002491", "rank": 1}]))
    monkeypatch.setattr(
        srv,
        "get_strategy_decision_packet",
        lambda *a, **k: {
            "data_mode": "strategy_decision_packet",
            "results": [
                {
                    "symbol": "002491",
                    "signal_count": 0,
                    "first_triggered_at": "",
                    "pattern_diagnostics": {
                        "crossed_previous_high": True,
                        "first_cross_time": "09:31",
                        "opening_window_crossed_previous_high": True,
                        "no_signal_reason": "opening_breakout_candidate_but_no_qualified_pullback_resurge",
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(srv, "get_second_board_next_day_outcomes", lambda *a, **k: {"outcomes": []})

    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")

    assert res["triggered_count"] == 0
    assert res["per_pick"][0]["triggered"] is False
    assert res["per_pick"][0]["crossed_previous_high"] is True
    assert res["per_pick"][0]["cross_time"] == "09:31"
    assert res["per_pick"][0]["no_signal_reason"] == "opening_breakout_candidate_but_no_qualified_pullback_resurge"


def test_trigger_validation_maps_sealed_next_day_field(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    srv.record_selection_audit("2026-06-18", json.dumps([{"symbol": "002491", "rank": 1}]))
    monkeypatch.setattr(
        srv,
        "_validation_intraday_trigger",
        lambda *a: {
            "triggered": True,
            "crossed_previous_high": True,
            "trigger_time": "09:41",
            "cross_time": "09:32",
            "no_signal_reason": "signal_triggered",
            "data_mode": "ok",
        },
    )
    monkeypatch.setattr(
        srv,
        "get_second_board_next_day_outcomes",
        lambda *a, **k: {
            "outcomes": [
                {"symbol": "002491", "sealed_next_day": True, "next_day_open_pct": 3.2}
            ]
        },
    )

    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")

    assert res["per_pick"][0]["sealed_second_board"] is True


def test_trigger_validation_includes_trend_outcome(monkeypatch, tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    srv.record_selection_audit("2026-06-18", json.dumps([{"symbol": "002491", "rank": 1}]))
    monkeypatch.setattr(
        srv,
        "_validation_intraday_trigger",
        lambda *a: {
            "triggered": True,
            "crossed_previous_high": True,
            "trigger_time": "09:41",
            "cross_time": "09:32",
            "no_signal_reason": "signal_triggered",
            "data_mode": "ok",
        },
    )
    monkeypatch.setattr(
        srv,
        "_validation_next_day_outcome",
        lambda *a: {"sealed_second_board": None, "next_day_open_pct": 1.2, "data_mode": "ok"},
    )
    monkeypatch.setattr(
        srv,
        "get_strategy_trend_outcomes",
        lambda *a, **k: {
            "data_mode": "strategy_trend_outcomes",
            "outcomes": [
                {
                    "symbol": "002491",
                    "data_mode": "trend_window_outcome",
                    "outcome_label": "gap_and_fade",
                    "trigger_outcome_label": "triggered_but_faded",
                    "max_gain_pct": 8.4,
                    "window_end_pct": 1.1,
                    "drawdown_after_high_pct": -6.2,
                }
            ],
        },
    )

    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")

    assert res["per_pick"][0]["trend_outcome_label"] == "gap_and_fade"
    assert res["per_pick"][0]["trigger_outcome_label"] == "triggered_but_faded"
    assert res["per_pick"][0]["max_gain_pct"] == 8.4
