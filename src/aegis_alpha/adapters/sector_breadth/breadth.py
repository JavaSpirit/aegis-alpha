from __future__ import annotations

from typing import Any


def compute_sector_breadth(
    *,
    theme: str,
    members: list[str],
    limitup_symbols: set[str],
    concept_system: str = "ths",
    data_source: str = "akshare",
) -> dict[str, Any]:
    """全市场板块宽度的纯计算(facts-only,无 I/O)。

    limitup_count = 成分股 ∩ 当日涨停池。非成分股的涨停不计入。
    """
    if not members:
        return {
            "theme": theme,
            "data_mode": "unavailable",
            "member_count": 0,
            "limitup_count": 0,
            "limitup_ratio": 0.0,
            "concept_system": concept_system,
            "data_source": data_source,
            "limitup_members": [],
            "notes": ["成分股列表为空,无法计算板块宽度。"],
        }
    member_set = {str(m).strip().upper().split(".", 1)[0] for m in members}
    hit = {str(s).strip().upper().split(".", 1)[0] for s in limitup_symbols} & member_set
    limitup_count = len(hit)
    return {
        "theme": theme,
        "data_mode": "computed",
        "member_count": len(member_set),
        "limitup_count": limitup_count,
        "limitup_ratio": round(limitup_count / len(member_set), 6),
        "concept_system": concept_system,
        "data_source": data_source,
        "limitup_members": sorted(hit),
    }


def compute_breadth_continuity(
    *,
    theme: str,
    daily_limitup_counts: list[int],
) -> dict[str, Any]:
    """两周(默认 ~10-14 交易日)板块持续性,facts-only。

    label 规则(描述性,非评分):
      - 无数据                          → unavailable
      - active_days >= 6 且后半段仍活跃 → persistent
      - 仅前半段活跃、后半段归零        → fading
      - active_days 1-2                 → emerging
      - 其余                            → weak
    """
    if not daily_limitup_counts:
        return {"theme": theme, "data_mode": "unavailable",
                "active_days": 0, "total_limitups": 0, "max_daily": 0,
                "recent_counts": [], "continuity_label": "unavailable"}
    counts = [int(c) for c in daily_limitup_counts]
    active_days = sum(1 for c in counts if c > 0)
    total = sum(counts)
    max_daily = max(counts)
    half = len(counts) // 2 or 1
    first_half_active = any(c > 0 for c in counts[:half])
    second_half_active = any(c > 0 for c in counts[half:])
    if active_days >= 6 and second_half_active:
        label = "persistent"
    elif first_half_active and not second_half_active:
        label = "fading"
    elif active_days <= 2:
        label = "emerging"
    else:
        label = "weak"
    return {
        "theme": theme,
        "data_mode": "computed",
        "active_days": active_days,
        "total_limitups": total,
        "max_daily": max_daily,
        "recent_counts": counts[-5:],
        "continuity_label": label,
    }
