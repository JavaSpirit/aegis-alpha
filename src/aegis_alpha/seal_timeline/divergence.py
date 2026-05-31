from __future__ import annotations

import hashlib

from aegis_alpha.clock import now_iso
from aegis_alpha.models import MarketEvent, ThemeLeader
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker


def detect_theme_divergence(
    leaders: list[ThemeLeader],
    tracker: SealTimelineTracker,
    *,
    trading_day: str,
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    received_at = now_iso()
    for leader in leaders:
        leader_timeline = tracker.get_timeline(leader.leader_symbol, trading_day)
        if leader_timeline.final_status not in {"broken"}:
            continue
        alive_followers = []
        for follower in leader.co_leader_symbols:
            follower_timeline = tracker.get_timeline(follower, trading_day)
            if follower_timeline.final_status in {"sealed", "reopened"}:
                alive_followers.append(follower)
        if not alive_followers:
            continue
        evidence = [
            f"Leader {leader.leader_symbol} broken in theme {leader.theme}; alive followers: {','.join(alive_followers)}.",
        ]
        seed = f"THEME_DIVERGENCE|{leader.theme}|{leader.leader_symbol}|{trading_day}"
        event_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        events.append(
            MarketEvent(
                event_id=event_id,
                event_type="THEME_DIVERGENCE",
                symbol=leader.leader_symbol,
                name=leader.leader_name,
                theme=leader.theme,
                confidence="medium",
                score=70.0,
                evidence=evidence,
                provider_timestamp=received_at,
                received_at=received_at,
                freshness_status="fresh",
                suggested_agent_action=[
                    "warn_orderbook_risk",
                    "rescore_second_board_candidates",
                ],
                data={
                    "leader_symbol": leader.leader_symbol,
                    "alive_followers": alive_followers,
                    "trading_day": trading_day,
                },
            )
        )
    return events
