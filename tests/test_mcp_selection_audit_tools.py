from __future__ import annotations

import json
from aegis_alpha.mcp import server


def test_record_and_get_selection_audit_roundtrip(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)

    picks = json.dumps([{"symbol": "002491", "rank": 1, "relative_reason": "胜过X", "caveats": []}])
    rec = server.record_selection_audit("2026-06-19", picks, candidate_pool_size=55)
    assert rec["as_of_day"] == "2026-06-19"
    assert rec["equals_baseline"] in (True, False)
    assert "confidence_label" in rec
    assert rec["audit_quality"] == "ok"

    got = server.get_selection_audit("2026-06-19")
    assert got["picks"][0]["symbol"] == "002491"
    assert got["data_mode"] == "ok"


def test_get_selection_audit_unavailable(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    res = server.get_selection_audit("2099-01-01")
    assert res["data_mode"] == "unavailable"


def test_record_with_rejected_roundtrips(monkeypatch, tmp_path):
    import json
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    picks = json.dumps([{"symbol": "002491", "rank": 1}])
    rejected = json.dumps([{"symbol": "300475", "why_rejected": "题材分歧", "beat_by": "002491"}])
    server.record_selection_audit("2026-06-19", picks, rejected_json=rejected)
    got = server.get_selection_audit("2026-06-19")
    assert got["rejected"][0]["symbol"] == "300475"
    assert got["rejected"][0]["beat_by"] == "002491"


def test_record_selection_audit_flags_incomplete_agent_explanation(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)

    picks = json.dumps([{"symbol": "002491"}])
    rejected = json.dumps([{"symbol": "300475"}])

    rec = server.record_selection_audit("2026-06-19", picks, rejected_json=rejected)

    assert rec["audit_quality"] == "incomplete"
    assert "audit_quality_warnings" in rec
    assert any("002491: rank" in item for item in rec["audit_quality_warnings"])
    assert any("002491: relative_reason" in item for item in rec["audit_quality_warnings"])
    assert any("300475: why_rejected" in item for item in rec["audit_quality_warnings"])
    assert any("300475: beat_by" in item for item in rec["audit_quality_warnings"])


def test_record_equals_baseline_when_picks_match_seal_amount_top(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    # Stub the historical candidates so the seal_amount baseline TopN == agent picks
    monkeypatch.setattr(
        server, "get_historical_second_board_candidates",
        lambda day, limit=50: [
            {"symbol": "002491", "seal_amount_cny": 9e8, "seal_to_turnover_ratio": 0.3, "first_limit_up_time": "09:31"},
            {"symbol": "300475", "seal_amount_cny": 1e8, "seal_to_turnover_ratio": 0.9, "first_limit_up_time": "09:45"},
        ],
    )
    picks = json.dumps([{"symbol": "002491", "rank": 1}])  # top-1 by seal_amount is 002491
    rec = server.record_selection_audit("2026-06-19", picks)
    assert rec["equals_baseline"] is True
    assert "anti_mechanical_warning" in rec
