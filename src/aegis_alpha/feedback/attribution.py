from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    MarketAction,
    OutcomeAttribution,
    OutcomeAttributionTag,
    ThemeLeaderRole,
)
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


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


# Note: the OutcomeAttributionTag literal includes "theme_breadth_collapsed",
# but it is not yet wired into the rule chain below. Reserved for a future rule
# that detects board-wide breadth collapse during the trading day. Until then,
# this tag is unreachable.
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


def attribute_from_stored_data(
    *,
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    symbol: str,
    trading_day: str,
) -> OutcomeAttribution | None:
    """Resolve attribution by joining historical snapshot + outcome + theme leader.

    Returns None when no outcome row exists for (symbol, trading_day) — there is
    nothing to attribute.
    """
    outcome = store.get_review_outcome(symbol, trading_day)
    # get_review_outcome returns a placeholder when missing; sealed_second_board is
    # only meaningful when actually recorded
    if outcome.touched_limit_up is None and outcome.sealed_second_board is None:
        return None

    snap = store.get_historical_snapshot(symbol, trading_day)
    if snap is None:
        return None

    raw: dict = {}
    try:
        raw = json.loads(snap.payload_json or "{}")
    except json.JSONDecodeError:
        raw = {}

    leader_symbol = raw.get("theme_leader_symbol", "") or symbol
    leader_status = "unknown"
    try:
        timeline = adapter.get_seal_timeline(leader_symbol, trading_day)
        leader_status = timeline.final_status
    except Exception:
        leader_status = "unknown"

    market_action = "selective"
    try:
        gate = adapter.get_market_sentiment_gate()
        market_action = gate.action
    except Exception:
        market_action = "selective"

    inputs = AttributionInputs(
        symbol=symbol,
        trading_day=trading_day,
        sealed_second_board=bool(outcome.sealed_second_board),
        theme=snap.theme,
        theme_role=snap.theme_role,
        theme_leader_symbol=leader_symbol,
        theme_leader_final_status=leader_status,
        market_action=market_action,
        auction_change_pct=float(raw.get("auction_change_pct") or 0.0),
        first_limit_up_time=str(raw.get("first_limit_up_time") or "unknown"),
        seal_decay_pct=float(raw.get("seal_decay_pct") or 0.0),
        previous_consecutive_boards=snap.previous_consecutive_boards,
    )
    attribution = attribute_outcome(inputs)
    store.save_attribution(attribution)
    return attribution
