from __future__ import annotations

import hashlib
from typing import Any


def compute_audit_id(as_of_day: str, pick_symbols: list[str]) -> str:
    """幂等哈希:同 as_of_day + 同组 picks(顺序无关)→ 同 ID。"""
    norm = "|".join(sorted(str(s).strip().upper() for s in pick_symbols))
    raw = f"{as_of_day}::{norm}"
    return "sa_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def compute_equals_baseline(pick_symbols: list[str], baseline: dict[str, Any]) -> bool:
    """agent TopN 是否与任一朴素基准 TopN 的 symbol 集合完全相同(反机械排序)。"""
    pick_set = {str(s).strip().upper() for s in pick_symbols}
    if not pick_set:
        return False
    for key in ("seal_amount", "seal_ratio", "first_seal_time"):
        base_list = baseline.get(key) or []
        base_set = {str(s).strip().upper() for s in base_list}
        if base_set and base_set == pick_set:
            return True
    return False


def compute_confidence_label(*, accumulated_days: int) -> str:
    """样本 <10 交易日强制 exploratory;>=10 给 low(默认保守)。"""
    if accumulated_days < 10:
        return "exploratory"
    return "low"
