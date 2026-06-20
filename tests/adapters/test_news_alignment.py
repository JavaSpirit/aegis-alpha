from __future__ import annotations

from aegis_alpha.adapters.news_alignment.alignment import compute_news_alignment


def test_alignment_matches_keyword():
    docs = [
        {"title": "国家发改委发布算力基础设施新政", "date": "2026-06-18"},
        {"title": "某公司中标数据中心项目", "date": "2026-06-17"},
        {"title": "无关公告", "date": "2026-06-16"},
    ]
    result = compute_news_alignment(query="算力", docs=docs)
    assert result["matched_count"] == 1
    assert result["alignment_strength"] in {"weak", "medium"}
    assert result["source_is_caixin"] is False


def test_alignment_none_when_no_match():
    result = compute_news_alignment(query="低空经济", docs=[{"title": "算力新政", "date": "2026-06-18"}])
    assert result["matched_count"] == 0
    assert result["alignment_strength"] == "none"


def test_alignment_empty_docs_unavailable():
    result = compute_news_alignment(query="x", docs=[])
    assert result["data_mode"] == "unavailable"
    assert result["matched_count"] == 0
    assert result["source_is_caixin"] is False
