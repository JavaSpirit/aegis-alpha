from __future__ import annotations

from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import HistoricalCandidateSnapshot
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


def backfill_candidates(
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    *,
    trading_days: Iterable[str],
) -> int:
    """Snapshot the current adapter candidate pool for each requested trading_day label.

    The mock adapter returns the same pool regardless of trading_day so this
    is deterministic for tests. The jvquant adapter returns whatever its
    semantic queries produce now — backfill is meant to be re-run daily as
    a cron job to capture each day's candidate pool.

    Returns the count of HistoricalCandidateSnapshot rows persisted (one per
    candidate per trading_day).
    """
    persisted = 0
    timestamp = now_iso()
    days = [day.strip() for day in trading_days if day.strip()]
    for trading_day in days:
        candidates = adapter.get_second_board_candidates()
        for candidate in candidates:
            snap = HistoricalCandidateSnapshot(
                symbol=candidate.symbol,
                trading_day=trading_day,
                grade_at_pick=candidate.grade,
                grade_reason=candidate.grade_reason,
                theme=candidate.theme,
                theme_role=candidate.theme_role,
                previous_consecutive_boards=candidate.previous_consecutive_boards,
                payload_json=candidate.model_dump_json(),
                created_at=timestamp,
            )
            store.save_historical_snapshot(snap)
            persisted += 1
    return persisted
