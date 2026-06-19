from __future__ import annotations

from aegis_alpha.adapters.sector_breadth.breadth import compute_breadth_continuity
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
    assert result["limitup_members"] == []


def test_continuity_labels_persistent():
    # 10 个交易日,7 天有涨停 → persistent
    daily_counts = [2, 0, 3, 1, 0, 2, 4, 0, 1, 2]
    result = compute_breadth_continuity(theme="AI算力", daily_limitup_counts=daily_counts)
    assert result["active_days"] == 7
    assert result["total_limitups"] == 15
    assert result["max_daily"] == 4
    assert result["continuity_label"] == "persistent"


def test_continuity_label_fading():
    daily_counts = [5, 4, 3, 0, 0, 0, 0, 0, 0, 0]
    result = compute_breadth_continuity(theme="x", daily_limitup_counts=daily_counts)
    assert result["continuity_label"] == "fading"


def test_continuity_empty_is_unavailable():
    result = compute_breadth_continuity(theme="x", daily_limitup_counts=[])
    assert result["data_mode"] == "unavailable"
