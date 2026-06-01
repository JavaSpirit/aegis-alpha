from __future__ import annotations

import hashlib
from dataclasses import dataclass

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    MarketEvent,
    SectorRotationEvidence,
    ThemeLeader,
)


# CALIBRATE: see config/p6_thresholds.yaml § sector_events.break_board_base_score
_BREAK_BOARD_BASE_SCORE = 60.0
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.break_board_height_bonus
_BREAK_BOARD_HEIGHT_BONUS = 5.0  # 每多一个连板 +5 分
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.rotation_base_score
_ROTATION_BASE_SCORE = 65.0
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.rotation_follower_bonus
_ROTATION_FOLLOWER_BONUS = 3.0  # 每一个 strengthening alive follower +3 分


@dataclass(frozen=True)
class LeaderBreakInputs:
    leaders: list[ThemeLeader]
    trading_day: str
    min_consecutive_boards: int = 2


@dataclass(frozen=True)
class SectorRotationInputs:
    leaders: list[ThemeLeader]
    trading_day: str
    min_strengthening_alive: int = 3


def _event_id(prefix: str, parts: list[str]) -> str:
    seed = prefix + "|" + "|".join(parts)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def detect_theme_leader_break_board(
    inputs: LeaderBreakInputs,
) -> list[MarketEvent]:
    """When a high-height (>= min_consecutive_boards) leader breaks, emit
    THEME_LEADER_BREAK_BOARD events for the theme."""
    events: list[MarketEvent] = []
    timestamp = now_iso()
    for leader in inputs.leaders:
        if leader.leader_status != "broken":
            continue
        if leader.leader_consecutive_boards < inputs.min_consecutive_boards:
            continue
        score = min(
            100.0,
            _BREAK_BOARD_BASE_SCORE
            + _BREAK_BOARD_HEIGHT_BONUS * float(leader.leader_consecutive_boards),
        )
        events.append(
            MarketEvent(
                event_id=_event_id(
                    "THEME_LEADER_BREAK_BOARD",
                    [leader.theme, leader.leader_symbol, inputs.trading_day],
                ),
                event_type="THEME_LEADER_BREAK_BOARD",
                symbol=leader.leader_symbol,
                name=leader.leader_name,
                theme=leader.theme,
                confidence="medium",
                score=score,
                evidence=[
                    f"theme={leader.theme}",
                    f"leader={leader.leader_symbol}",
                    f"consecutive={leader.leader_consecutive_boards}",
                    f"final_status={leader.leader_status}",
                ],
                provider_timestamp=timestamp,
                received_at=timestamp,
                freshness_status="fresh",
                suggested_agent_action=[
                    "downgrade_followers_in_same_theme",
                    "explain_break_board_risk_to_user",
                ],
                data={
                    "trading_day": inputs.trading_day,
                    "theme": leader.theme,
                    "leader_symbol": leader.leader_symbol,
                    "consecutive_boards": leader.leader_consecutive_boards,
                    "co_leader_symbols": list(leader.co_leader_symbols),
                },
            )
        )
    return events


def detect_sector_rotation(
    inputs: SectorRotationInputs,
) -> list[MarketEvent]:
    """When one theme's leader is broken AND another theme's leader is sealed
    with N>= alive followers, emit a SECTOR_ROTATION event linking the two."""
    events: list[MarketEvent] = []
    timestamp = now_iso()
    weak: list[ThemeLeader] = []
    strong: list[ThemeLeader] = []
    for leader in inputs.leaders:
        if leader.leader_status == "broken":
            weak.append(leader)
        elif leader.leader_status in {"sealed", "reopened"}:
            if leader.member_count >= inputs.min_strengthening_alive:
                strong.append(leader)
    if not weak or not strong:
        return events
    for w in weak:
        for s in strong:
            if w.theme == s.theme:
                continue
            evidence_model = SectorRotationEvidence(
                weakening_theme=w.theme,
                weakening_leader_status=w.leader_status,
                strengthening_theme=s.theme,
                strengthening_leader_status=s.leader_status,
                weakening_alive_count=0,
                strengthening_alive_count=s.member_count,
            )
            score = min(
                100.0,
                _ROTATION_BASE_SCORE
                + _ROTATION_FOLLOWER_BONUS * float(s.member_count),
            )
            events.append(
                MarketEvent(
                    event_id=_event_id(
                        "SECTOR_ROTATION",
                        [w.theme, s.theme, inputs.trading_day],
                    ),
                    event_type="SECTOR_ROTATION",
                    symbol="",
                    name="",
                    theme=s.theme,
                    confidence="medium",
                    score=score,
                    evidence=[
                        f"weakening_theme={w.theme}",
                        f"strengthening_theme={s.theme}",
                        f"strengthening_alive={s.member_count}",
                    ],
                    provider_timestamp=timestamp,
                    received_at=timestamp,
                    freshness_status="fresh",
                    suggested_agent_action=[
                        "rerank_themes",
                        "watch_strengthening_theme_followers",
                    ],
                    data=evidence_model.model_dump(),
                )
            )
    return events
