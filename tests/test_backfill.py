from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.feedback.backfill import backfill_candidates
from aegis_alpha.storage import AegisAlphaStore


def test_backfill_persists_candidates_for_today(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    persisted = backfill_candidates(adapter, store, trading_days=["2026-05-31"])

    assert persisted >= 1
    rows = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    assert {row.symbol for row in rows} == {"002230.SZ", "300024.SZ"}
    kdxf = next(row for row in rows if row.symbol == "002230.SZ")
    assert kdxf.theme == "AI应用"
    assert kdxf.theme_role == "leader"


def test_backfill_idempotent_on_same_day(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    first = backfill_candidates(adapter, store, trading_days=["2026-05-31"])
    second = backfill_candidates(adapter, store, trading_days=["2026-05-31"])

    assert first == second
    rows = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    assert len(rows) == 2


def test_backfill_multiple_days(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    persisted = backfill_candidates(adapter, store, trading_days=["2026-05-30", "2026-05-31"])

    rows_30 = store.list_historical_snapshots_between(start_day="2026-05-30", end_day="2026-05-30")
    rows_31 = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    assert len(rows_30) == 2
    assert len(rows_31) == 2
    assert persisted == 4
