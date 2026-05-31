from __future__ import annotations

import hashlib
from dataclasses import dataclass

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    MarketAction,
    OutcomeAttribution,
    OutcomeAttributionTag,
    ThemeLeaderRole,
)


@dataclass(frozen=True)
class AttributionInputs:
    symbol: str
    trading_day: str
    sealed_second_board: bool
    theme: str
    theme_role: ThemeLeaderRole
    theme_leader_symbol: str
    theme_leader_final_status: str  # "sealed" / "broken" / "reopened" / "unknown"
    market_action: MarketAction
    auction_change_pct: float
    first_limit_up_time: str
    seal_decay_pct: float
    previous_consecutive_boards: int


_HIGH_OPEN_THRESHOLD = 3.0  # 竞价高开 > 3% 视为风险
_LATE_SEAL_CUTOFF = "10:30:00"
_SEAL_DECAY_THRESHOLD = 30.0


def _attribution_id(symbol: str, trading_day: str) -> str:
    seed = f"{symbol}|{trading_day}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def attribute_outcome(inputs: AttributionInputs) -> OutcomeAttribution:
    evidence: list[str] = []
    secondary: list[OutcomeAttributionTag] = []

    if inputs.sealed_second_board:
        return OutcomeAttribution(
            attribution_id=_attribution_id(inputs.symbol, inputs.trading_day),
            symbol=inputs.symbol,
            trading_day=inputs.trading_day,
            primary_tag="no_clear_attribution",
            secondary_tags=[],
            evidence=["Candidate sealed second board; no failure to attribute."],
            created_at=now_iso(),
        )

    primary: OutcomeAttributionTag = "no_clear_attribution"

    # Rule 1: market_gate_turned_avoid 优先级最高（结构性问题）
    if inputs.market_action == "avoid":
        primary = "market_gate_turned_avoid"
        evidence.append(f"market_action={inputs.market_action} when candidate failed to seal.")

    # Rule 2: leader_break_down——follower 且龙头炸板
    elif inputs.theme_role in {"follower", "co_leader"} and inputs.theme_leader_final_status == "broken":
        primary = "leader_break_down"
        evidence.append(
            f"Theme leader {inputs.theme_leader_symbol} broken in theme {inputs.theme}; "
            f"candidate is {inputs.theme_role}."
        )

    # Rule 3: seal_amount_decay——封单衰减大于阈值
    elif inputs.seal_decay_pct >= _SEAL_DECAY_THRESHOLD:
        primary = "seal_amount_decay"
        evidence.append(f"seal_decay_pct={inputs.seal_decay_pct:.1f} >= {_SEAL_DECAY_THRESHOLD:.1f}.")

    # Rule 4: auction_high_open_too_far——竞价高开过多
    elif inputs.auction_change_pct >= _HIGH_OPEN_THRESHOLD:
        primary = "auction_high_open_too_far"
        evidence.append(
            f"auction_change_pct={inputs.auction_change_pct:.2f} >= {_HIGH_OPEN_THRESHOLD:.2f}."
        )

    # Rule 5: first_seal_too_late——首封时间晚（仅当 first_limit_up_time 不是 unknown 时检测）
    elif (
        inputs.first_limit_up_time
        and inputs.first_limit_up_time != "unknown"
        and inputs.first_limit_up_time > _LATE_SEAL_CUTOFF
    ):
        primary = "first_seal_too_late"
        evidence.append(
            f"first_limit_up_time={inputs.first_limit_up_time} > {_LATE_SEAL_CUTOFF}."
        )

    # Secondary tags collect non-primary risk signals for context
    if primary != "auction_high_open_too_far" and inputs.auction_change_pct >= _HIGH_OPEN_THRESHOLD:
        secondary.append("auction_high_open_too_far")
    if (
        primary != "first_seal_too_late"
        and inputs.first_limit_up_time
        and inputs.first_limit_up_time != "unknown"
        and inputs.first_limit_up_time > _LATE_SEAL_CUTOFF
    ):
        secondary.append("first_seal_too_late")

    if not evidence:
        evidence.append("No clear attribution signal matched; outcome remains unexplained.")

    return OutcomeAttribution(
        attribution_id=_attribution_id(inputs.symbol, inputs.trading_day),
        symbol=inputs.symbol,
        trading_day=inputs.trading_day,
        primary_tag=primary,
        secondary_tags=secondary,
        evidence=evidence,
        created_at=now_iso(),
    )
