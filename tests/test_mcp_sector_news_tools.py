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


def test_sector_breadth_continuity_handles_list_of_dicts(monkeypatch):
    """Real jvquant adapter returns daily_counts as list-of-dicts; must compute, not crash."""

    class _FakeAdapter:
        def get_theme_continuity(self, theme, as_of_day, lookback_days):
            return {
                "daily_counts": [
                    {"trading_day": "2026-06-1%d" % d, "limit_up_count": c}
                    for d, c in enumerate([2, 0, 3, 1, 0, 2, 4, 0, 1, 2], start=1)
                ]
            }

    monkeypatch.setattr(server, "get_market_data_adapter", lambda: _FakeAdapter())
    result = server.get_sector_breadth_continuity("AI算力", "2026-06-18")
    assert result.get("data_mode") == "computed"
    assert result.get("active_days") == 7
    assert result.get("continuity_label") == "persistent"
