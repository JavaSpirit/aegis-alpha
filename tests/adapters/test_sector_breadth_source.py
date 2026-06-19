from __future__ import annotations

from aegis_alpha.adapters.sector_breadth import akshare_source


def test_fetch_members_degrades_when_source_raises(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("akshare unavailable")
    monkeypatch.setattr(akshare_source, "_load_concept_members_raw", boom)
    result = akshare_source.fetch_theme_members("AI算力")
    assert result["data_mode"] == "unavailable"
    assert result["members"] == []
    assert "akshare" in result["data_source"]
    assert result["theme"] == "AI算力"


def test_fetch_members_ok_when_source_returns(monkeypatch):
    monkeypatch.setattr(
        akshare_source, "_load_concept_members_raw",
        lambda theme: ["000001", "000002", "000003"],
    )
    result = akshare_source.fetch_theme_members("AI算力")
    assert result["data_mode"] == "ok"
    assert result["members"] == ["000001", "000002", "000003"]
    assert result["concept_system"] == "ths"


def test_fetch_members_empty_is_unavailable(monkeypatch):
    monkeypatch.setattr(akshare_source, "_load_concept_members_raw", lambda theme: [])
    result = akshare_source.fetch_theme_members("x")
    assert result["data_mode"] == "unavailable"
    assert result["members"] == []
