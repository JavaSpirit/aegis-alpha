from __future__ import annotations

from aegis_alpha.adapters.news_alignment import cninfo_source


def test_fetch_docs_degrades_on_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("cninfo down")
    monkeypatch.setattr(cninfo_source, "_load_announcements_raw", boom)
    result = cninfo_source.fetch_recent_docs("算力", lookback_days=5)
    assert result["data_mode"] == "unavailable"
    assert result["docs"] == []
    assert result["source"] == "cninfo"
    assert result["error"]


def test_fetch_docs_ok(monkeypatch):
    monkeypatch.setattr(
        cninfo_source, "_load_announcements_raw",
        lambda q, d: [{"title": "算力新政", "date": "2026-06-18"}],
    )
    result = cninfo_source.fetch_recent_docs("算力", lookback_days=5)
    assert result["data_mode"] == "ok"
    assert result["docs"] == [{"title": "算力新政", "date": "2026-06-18"}]
    assert result["source"] == "cninfo"


def test_fetch_docs_empty_is_unavailable(monkeypatch):
    monkeypatch.setattr(cninfo_source, "_load_announcements_raw", lambda q, d: [])
    result = cninfo_source.fetch_recent_docs("x", lookback_days=5)
    assert result["data_mode"] == "unavailable"
    assert result["docs"] == []
