from __future__ import annotations

from dataclasses import dataclass, field

from aegis_alpha.models import LimitupDriverType


_POLICY_KEYWORDS: tuple[str, ...] = (
    "国务院",
    "国务院发布",
    "中央",
    "国家发改委",
    "工信部",
    "财政部",
    "证监会",
    "新基建",
    "十四五",
    "十五五",
    "政策",
    "补贴",
    "顶层设计",
)
# CALIBRATE: see config/p6_thresholds.yaml § limitup_driver.hot_money_net_buy_threshold
_HOT_MONEY_NET_BUY_THRESHOLD = 10_000_000.0


@dataclass(frozen=True)
class LimitupDriverInputs:
    symbol: str
    concept_tags: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    list_reason: str = ""
    net_amount_cny: float = 0.0
    previous_consecutive_boards: int = 0
    recent_earnings_surprise: bool = False
    recent_policy_keywords: list[str] = field(default_factory=list)


def _hits_any(items: list[str], keywords: tuple[str, ...]) -> bool:
    if not items:
        return False
    bag = " ".join(str(s) for s in items if s)
    return any(kw and kw in bag for kw in keywords)


def classify_limitup_driver(inputs: LimitupDriverInputs) -> LimitupDriverType:
    """Classify the driver of a limit-up event into 4 buckets:
    earnings / policy / theme / hot_money. Returns 'unknown' when no rule matches."""
    if inputs.recent_earnings_surprise:
        return "earnings"
    if (
        _hits_any(inputs.topic_tags, _POLICY_KEYWORDS)
        or _hits_any(inputs.concept_tags, _POLICY_KEYWORDS)
        or any(kw in inputs.list_reason for kw in _POLICY_KEYWORDS)
        or inputs.recent_policy_keywords
    ):
        return "policy"
    if (
        inputs.net_amount_cny >= _HOT_MONEY_NET_BUY_THRESHOLD
        and inputs.previous_consecutive_boards >= 1
    ):
        return "hot_money"
    if inputs.concept_tags or inputs.topic_tags:
        return "theme"
    return "unknown"
