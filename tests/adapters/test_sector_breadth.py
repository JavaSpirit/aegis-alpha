from __future__ import annotations

from aegis_alpha.adapters.sector_breadth.breadth import compute_sector_breadth


def test_breadth_counts_limitups_within_members():
    members = ["000001", "000002", "000003", "000004"]
    limitups = {"000001", "000003", "999999"}  # 999999 不在成分内,不计
    result = compute_sector_breadth(
        theme="AI算力", members=members, limitup_symbols=limitups,
        concept_system="ths", data_source="akshare",
    )
    assert result["theme"] == "AI算力"
    assert result["member_count"] == 4
    assert result["limitup_count"] == 2
    assert result["limitup_ratio"] == 0.5
    assert result["concept_system"] == "ths"
    assert result["data_source"] == "akshare"


def test_breadth_empty_members_is_unavailable():
    result = compute_sector_breadth(
        theme="x", members=[], limitup_symbols=set(),
        concept_system="ths", data_source="akshare",
    )
    assert result["data_mode"] == "unavailable"
    assert result["member_count"] == 0
