from __future__ import annotations

from aegis_alpha.mcp import server


def test_get_market_sector_breadth_tool_exists():
    assert hasattr(server, "get_market_sector_breadth")


def test_get_sector_breadth_continuity_tool_exists():
    assert hasattr(server, "get_sector_breadth_continuity")


def test_get_news_alignment_tool_exists():
    assert hasattr(server, "get_news_alignment")


def test_news_alignment_returns_facts(monkeypatch):
    from aegis_alpha.adapters.news_alignment import cninfo_source
    monkeypatch.setattr(
        cninfo_source, "_load_announcements_raw",
        lambda *a, **k: [{"title": "算力新政发布", "date": "2026-06-18"}],
    )
    result = server.get_news_alignment("算力", lookback_days=5)
    assert result["matched_count"] == 1
    assert result["source_is_caixin"] is False


def test_sector_breadth_degrades_when_members_unavailable(monkeypatch):
    from aegis_alpha.adapters.sector_breadth import akshare_source
    monkeypatch.setattr(
        akshare_source, "_load_concept_members_raw",
        lambda theme: (_ for _ in ()).throw(RuntimeError("akshare down")),
    )
    result = server.get_market_sector_breadth("2026-06-18", "AI算力")
    assert result["data_mode"] == "unavailable"
