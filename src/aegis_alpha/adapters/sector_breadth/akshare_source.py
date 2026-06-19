from __future__ import annotations

from typing import Any


def _load_concept_members_raw(theme: str) -> list[str]:
    """真实 AkShare 调用(THS 概念成分)。隔离成独立函数以便测试 monkeypatch。

    限速:调用方在批量遍历多板块时应自行 sleep,避免 429。
    """
    import akshare as ak  # lazy import — 缺失不影响其余模块

    df = ak.stock_board_concept_cons_ths(symbol=theme)
    if df.empty or df.columns.empty:
        return []
    col = "代码" if "代码" in df.columns else df.columns[0]
    return [str(v) for v in df[col].tolist()]


def fetch_theme_members(theme: str) -> dict[str, Any]:
    """取某 THS 概念的成分股列表。任何失败都降级为 unavailable,绝不抛。"""
    try:
        members = _load_concept_members_raw(theme)
    except Exception as exc:  # noqa: BLE001 — advisory source, never crash caller
        return {
            "theme": theme,
            "data_mode": "unavailable",
            "members": [],
            "data_source": "akshare.ths",
            "concept_system": "ths",
            "error": str(exc)[:200],
        }
    return {
        "theme": theme,
        "data_mode": "ok" if members else "unavailable",
        "members": members,
        "data_source": "akshare.ths",
        "concept_system": "ths",
    }
