"""Run one deterministic market-observer pass against the current DB.

This is the increment-1 stand-in for the Hermes agent job (increment 2). It does
NOT call an LLM. It reads the structured intraday market context, derives a
single honest, low-confidence AgentObservation from facts only, persists it, and
prints whether the deterministic notification policy would push it.

Purpose: prove the closed loop end-to-end — the system can produce an auditable
observation even when no BUYPOINT_ALERT fired — before wiring real agent judgment.

Usage:
    python scripts/market_observer_pass.py [--trading-day YYYY-MM-DD] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aegis_alpha.config import load_project_env
from aegis_alpha.feedback.agent_observation import (
    compute_observation_id,
    observation_notification_grade,
)
from aegis_alpha.mcp.server import get_intraday_market_context
from aegis_alpha.models import AgentObservation
from aegis_alpha.storage import AegisAlphaStore


def derive_observation(trading_day: str, context: dict) -> AgentObservation:
    """Turn the fact packet into one honest, deterministic observation.

    No LLM, no buy/sell stance inflation. The heuristic is conservative on
    purpose: it surfaces the strongest structured signal as a monitor-only
    watch, or flags a data gap when the context is empty. Real agent judgment
    replaces this in increment 2.
    """
    strongest = context.get("strongest_events") or []
    counts = context.get("event_count_by_type") or {}
    data_gaps = list(context.get("data_gaps") or [])

    if not strongest:
        return AgentObservation(
            observation_id=compute_observation_id(
                trading_day=trading_day, source="periodic_market_scan",
                observation_type="data_gap",
            ),
            trading_day=trading_day,
            source="periodic_market_scan",
            observation_type="data_gap",
            title="盘中无结构化事件",
            summary="本次扫描时窗内无结构化市场事件,可能盘前/无触发/feed 降级。",
            stance="insufficient_data",
            confidence="low",
            evidence=[f"runner_state={context.get('runner_state')}",
                      f"total_recent_events={context.get('total_recent_events', 0)}"],
            data_gaps=data_gaps or ["无近期结构化事件可供观察。"],
            provider="deterministic_observer_pass",
            model="heuristic_v1",
        )

    top = strongest[0]
    theme = top.get("theme", "") or ""
    return AgentObservation(
        observation_id=compute_observation_id(
            trading_day=trading_day, source="periodic_market_scan",
            observation_type="watchlist_observation",
            symbol=top.get("symbol", ""), theme=theme,
        ),
        trading_day=trading_day,
        source="periodic_market_scan",
        observation_type="watchlist_observation",
        symbol=top.get("symbol", ""),
        theme=theme,
        title=f"最强结构化事件 {top.get('event_type')} {top.get('symbol')}",
        summary=(
            f"本次扫描最强事件为 {top.get('event_type')} (score={top.get('score')}); "
            f"事件类型分布 {counts}。仅为事实观察,非买卖结论。"
        ),
        stance="monitor_only",
        confidence="low",
        evidence=[
            f"strongest_event={top.get('event_type')} symbol={top.get('symbol')} score={top.get('score')}",
            f"event_count_by_type={counts}",
            f"freshness={context.get('freshness')}",
        ],
        data_gaps=data_gaps or ["确定性观察器无主动买盘方向与同题材联动判断,留待 agent。"],
        provider="deterministic_observer_pass",
        model="heuristic_v1",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one deterministic market-observer pass.")
    parser.add_argument("--trading-day", default="", help="Trading day YYYY-MM-DD (default: today, SH tz).")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist; just print what would happen.")
    args = parser.parse_args()

    load_project_env()
    tz = ZoneInfo("Asia/Shanghai")
    trading_day = args.trading_day or datetime.now(tz).date().isoformat()

    context = get_intraday_market_context()
    observation = derive_observation(trading_day, context)
    grade = observation_notification_grade(observation)

    persisted = False
    if not args.dry_run:
        store = AegisAlphaStore()
        saved = store.save_agent_observation(observation)
        observation = saved
        persisted = True

    would_notify = grade in ("urgent", "important")
    print(
        json.dumps(
            {
                "trading_day": trading_day,
                "dry_run": args.dry_run,
                "persisted": persisted,
                "observation_id": observation.observation_id,
                "observation_type": observation.observation_type,
                "stance": observation.stance,
                "confidence": observation.confidence,
                "notification_grade": grade,
                "would_notify_weclaw": would_notify,
                "title": observation.title,
                "summary": observation.summary,
                "evidence": observation.evidence,
                "data_gaps": observation.data_gaps,
                "context_runner_state": context.get("runner_state"),
                "context_total_events": context.get("total_recent_events"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
