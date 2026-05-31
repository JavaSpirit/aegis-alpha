from __future__ import annotations

from pathlib import Path

import pytest

from aegis_alpha.storage import AegisAlphaStore
from aegis_alpha.watchlists.manager import WatchlistManager


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_create_watchlist_assigns_id_and_persists(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))

    wl = manager.create(owner="user", label="2026-05-31 morning radar", symbols=["002230.SZ", "300024.SZ"])

    assert wl.watchlist_id
    assert wl.owner == "user"
    assert wl.status == "active"
    assert {entry.symbol for entry in wl.entries} == {"002230.SZ", "300024.SZ"}

    fetched = manager.get(wl.watchlist_id)
    assert fetched is not None
    assert {entry.symbol for entry in fetched.entries} == {"002230.SZ", "300024.SZ"}


def test_update_state_records_grade_change(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["002230.SZ"])

    manager.update_state(wl.watchlist_id, "002230.SZ", new_grade="A", action="promoted", note="seal stable")

    fetched = manager.get(wl.watchlist_id)
    assert fetched is not None
    entry = next(e for e in fetched.entries if e.symbol == "002230.SZ")
    assert entry.last_grade == "A"
    assert entry.last_action == "promoted"
    assert any("seal stable" in note for note in entry.notes)


def test_diff_against_prior_snapshot_lists_added_dropped_grade_changes(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["A", "B"])
    snap_before = manager.snapshot(wl.watchlist_id)
    manager.update_state(wl.watchlist_id, "A", new_grade="A", action="promoted")
    manager.add_symbols(wl.watchlist_id, ["C"])
    manager.drop_symbols(wl.watchlist_id, ["B"])
    snap_after = manager.snapshot(wl.watchlist_id)

    diff = manager.diff(snap_before, snap_after)

    assert diff.added_symbols == ["C"]
    assert diff.dropped_symbols == ["B"]
    assert diff.grade_changes["A"] == {"from": "C", "to": "A"}


def test_close_watchlist_sets_status(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["A"])

    closed = manager.close(wl.watchlist_id, note="end of day")

    assert closed.status == "closed"
    assert closed.closed_at
    assert any("end of day" in note for note in closed.notes)


def test_list_active_for_owner(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl_a = manager.create(owner="alice", label="a", symbols=["X"])
    wl_b = manager.create(owner="alice", label="b", symbols=["Y"])
    manager.create(owner="bob", label="c", symbols=["Z"])
    manager.close(wl_b.watchlist_id)

    active = manager.list_active(owner="alice")

    assert {item.watchlist_id for item in active} == {wl_a.watchlist_id}
