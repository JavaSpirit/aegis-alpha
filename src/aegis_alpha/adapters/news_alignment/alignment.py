from __future__ import annotations

from typing import Any


def compute_news_alignment(
    *,
    query: str,
    docs: list[dict[str, Any]],
    source: str = "cninfo",
) -> dict[str, Any]:
    """题材/个股的合规新闻对齐(facts-only,关键词匹配)。

    docs: 已取回的公告/新闻列表,每条至少含 'title'。
    这是合规替代(巨潮公告/Tushare 新闻),NOT 财联社电报。
    """
    if not docs:
        return {
            "query": query,
            "data_mode": "unavailable",
            "matched_count": 0,
            "alignment_strength": "none",
            "source": source,
            "source_is_caixin": False,
            "matched_titles": [],
            "notes": ["无可用公告/新闻,无法做题材对齐。"],
        }
    q = query.strip()
    matched = [d for d in docs if q and q in str(d.get("title", ""))]
    n = len(matched)
    if n == 0:
        strength = "none"
    elif n <= 2:
        strength = "weak"
    else:
        strength = "medium"
    return {
        "query": query,
        "data_mode": "computed",
        "matched_count": n,
        "alignment_strength": strength,
        "source": source,
        "source_is_caixin": False,
        "matched_titles": [str(d.get("title", "")) for d in matched[:10]],
        "notes": ["合规替代:巨潮公告/Tushare 新闻,非财联社电报原文。"],
    }
