from __future__ import annotations

import hashlib
from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import MarketEvent


# CALIBRATE: see config/p6_thresholds.yaml § contrarian_pool.recovery_threshold
_RECOVERY_THRESHOLD = 3  # 至少 3 只昨日跌停股今日 reverse 涨停才触发反向情绪事件
_MAX_SCORE = 100.0


def _event_id(trading_day: str, symbols: Iterable[str]) -> str:
    seed = "MARKET_BOTTOM_REVERSAL|" + trading_day + "|" + ",".join(sorted(symbols))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def detect_bottom_reversal(
    *,
    today_recovered_symbols: list[str],
    yesterday_limit_down_symbols: set[str],
    trading_day: str,
) -> MarketEvent | None:
    """When N>=_RECOVERY_THRESHOLD yesterday-limit-down stocks limit-up today,
    publish a MARKET_BOTTOM_REVERSAL event."""
    matched = [s for s in today_recovered_symbols if s in yesterday_limit_down_symbols]
    if len(matched) < _RECOVERY_THRESHOLD:
        return None
    score = min(_MAX_SCORE, 50.0 + 10.0 * len(matched))
    timestamp = now_iso()
    return MarketEvent(
        event_id=_event_id(trading_day, matched),
        event_type="MARKET_BOTTOM_REVERSAL",
        symbol="",
        name="",
        theme="contrarian",
        confidence="medium",
        score=score,
        evidence=[
            f"recovered_count={len(matched)}",
            f"sample_symbols={','.join(matched[:5])}",
        ],
        provider_timestamp=timestamp,
        received_at=timestamp,
        freshness_status="fresh",
        suggested_agent_action=[
            "explain context only; do not chase boards on reversal day",
            "treat as defensive market-wide signal, not single-stock trigger",
        ],
        data={"trading_day": trading_day, "recovered_symbols": matched},
    )
