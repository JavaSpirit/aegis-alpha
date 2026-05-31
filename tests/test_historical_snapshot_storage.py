from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_historical_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    snap = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="B",
        grade_reason="follower with strong seal",
        theme="AI",
        theme_role="follower",
        previous_consecutive_boards=2,
        payload_json='{"hello": "world"}',
        created_at="2026-05-31T15:30:00+08:00",
    )

    store.save_historical_snapshot(snap)
    fetched = store.get_historical_snapshot("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.grade_at_pick == "B"
    assert fetched.theme_role == "follower"


def test_save_historical_snapshot_upserts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    snap1 = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="C",
        created_at="2026-05-31T09:30:00+08:00",
    )
    snap2 = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="A",
        created_at="2026-05-31T09:35:00+08:00",
    )

    store.save_historical_snapshot(snap1)
    store.save_historical_snapshot(snap2)
    fetched = store.get_historical_snapshot("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.grade_at_pick == "A"


def test_list_historical_snapshots_between(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day in ("2026-05-25", "2026-05-26", "2026-05-27", "2026-05-30"):
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol="X",
                trading_day=day,
                grade_at_pick="B",
                created_at=f"{day}T09:30:00+08:00",
            )
        )

    rows = store.list_historical_snapshots_between(start_day="2026-05-26", end_day="2026-05-29")

    assert {row.trading_day for row in rows} == {"2026-05-26", "2026-05-27"}


def test_list_historical_snapshots_between_filters_by_symbol(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day in ("2026-05-26", "2026-05-27"):
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol="X",
                trading_day=day,
                grade_at_pick="B",
                created_at=f"{day}T09:30:00+08:00",
            )
        )
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol="Y",
                trading_day=day,
                grade_at_pick="C",
                created_at=f"{day}T09:30:00+08:00",
            )
        )

    rows = store.list_historical_snapshots_between(
        start_day="2026-05-26", end_day="2026-05-27", symbol="Y"
    )

    assert len(rows) == 2
    assert all(row.symbol == "Y" for row in rows)


def test_save_historical_snapshot_upsert_preserves_db_created_at(tmp_path: Path) -> None:
    import sqlite3
    store = _store(tmp_path)
    original_ts = "2026-05-31T09:30:00+08:00"
    store.save_historical_snapshot(
        HistoricalCandidateSnapshot(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            grade_at_pick="C",
            created_at=original_ts,
        )
    )
    store.save_historical_snapshot(
        HistoricalCandidateSnapshot(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            grade_at_pick="A",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT created_at FROM historical_candidate_snapshots WHERE symbol = ? AND trading_day = ?",
            ("002230.SZ", "2026-05-31"),
        ).fetchone()

    assert row is not None
    # The DB column (not the JSON payload) should retain the original ts.
    assert row[0] == original_ts
