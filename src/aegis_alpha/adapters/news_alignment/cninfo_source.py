from __future__ import annotations

from typing import Any


def _load_announcements_raw(query: str, lookback_days: int) -> list[dict[str, Any]]:
    """真实巨潮资讯取数(通过 akshare 封装的公开公告接口)。隔离以便测试 monkeypatch。

    巨潮是证监会指定的信息披露平台,公告完全公开合法。
    """
    import akshare as ak  # lazy import — 缺失不影响其余模块
    # query/lookback_days 暂未做服务端过滤,保留参数供后续按题材/时间窗筛选;当前取全部公告由上层 compute_news_alignment 关键词过滤。

    df = ak.stock_notice_report(symbol="全部")
    if df is None or df.empty or df.columns.empty:
        return []
    title_col = "公告标题" if "公告标题" in df.columns else df.columns[0]
    date_col = "公告日期" if "公告日期" in df.columns else df.columns[-1]
    docs: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        docs.append({"title": str(row[title_col]), "date": str(row[date_col])})
    return docs


def fetch_recent_docs(query: str, *, lookback_days: int = 7) -> dict[str, Any]:
    """取近 N 日公告(巨潮,免费合规)。任何失败都降级,绝不抛。"""
    try:
        docs = _load_announcements_raw(query, lookback_days)
    except Exception as exc:  # noqa: BLE001 — advisory source, never crash caller
        return {
            "query": query,
            "data_mode": "unavailable",
            "docs": [],
            "source": "cninfo",
            "error": str(exc)[:200],
        }
    return {
        "query": query,
        "data_mode": "ok" if docs else "unavailable",
        "docs": docs,
        "source": "cninfo",
    }
