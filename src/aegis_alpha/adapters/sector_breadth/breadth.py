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
