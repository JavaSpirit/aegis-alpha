from __future__ import annotations

import uuid
from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    CandidateGrade,
    Watchlist,
    WatchlistDiff,
    WatchlistEntry,
    WatchlistEntryAction,
)
from aegis_alpha.storage import AegisAlphaStore


class WatchlistManager:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def create(
        self,
        *,
        owner: str,
        label: str,
        symbols: Iterable[str],
        expires_at: str = "",
    ) -> Watchlist:
        timestamp = now_iso()
        watchlist = Watchlist(
            watchlist_id=str(uuid.uuid4()),
            owner=owner.strip(),
            label=label.strip(),
            status="active",
            created_at=timestamp,
            expires_at=expires_at.strip(),
            entries=[
                WatchlistEntry(
                    symbol=symbol.strip(),
                    added_at=timestamp,
                    initial_grade="C",
                    last_grade="C",
                    last_action="added",
                    last_action_at=timestamp,
                )
                for symbol in symbols
                if symbol.strip()
            ],
        )
        self.store.save_watchlist(watchlist)
        return watchlist

    def get(self, watchlist_id: str) -> Watchlist | None:
        return self.store.get_watchlist(watchlist_id)

    def list_active(self, *, owner: str = "") -> list[Watchlist]:
        return self.store.list_watchlists(owner=owner, status="active")

    def add_symbols(self, watchlist_id: str, symbols: Iterable[str]) -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        existing = {entry.symbol for entry in watchlist.entries}
        new_entries = [
            WatchlistEntry(
                symbol=symbol.strip(),
                added_at=timestamp,
                initial_grade="C",
                last_grade="C",
                last_action="added",
                last_action_at=timestamp,
            )
            for symbol in symbols
            if symbol.strip() and symbol.strip() not in existing
        ]
        if not new_entries:
            return watchlist
        watchlist = watchlist.model_copy(update={"entries": [*watchlist.entries, *new_entries]})
        self.store.save_watchlist(watchlist)
        return watchlist

    def drop_symbols(self, watchlist_id: str, symbols: Iterable[str]) -> Watchlist:
        watchlist = self._require(watchlist_id)
        targets = {symbol.strip() for symbol in symbols if symbol.strip()}
        kept = [entry for entry in watchlist.entries if entry.symbol not in targets]
        if len(kept) == len(watchlist.entries):
            return watchlist
        watchlist = watchlist.model_copy(update={"entries": kept})
        self.store.save_watchlist(watchlist)
        return watchlist

    def update_state(
        self,
        watchlist_id: str,
        symbol: str,
        *,
        new_grade: CandidateGrade,
        action: WatchlistEntryAction,
        note: str = "",
    ) -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        updated_entries: list[WatchlistEntry] = []
        for entry in watchlist.entries:
            if entry.symbol != symbol.strip():
                updated_entries.append(entry)
                continue
            notes = list(entry.notes)
            if note.strip():
                notes.append(f"{timestamp} {note.strip()}")
            updated_entries.append(
                entry.model_copy(
                    update={
                        "last_grade": new_grade,
                        "last_action": action,
                        "last_action_at": timestamp,
                        "notes": notes,
                    }
                )
            )
        watchlist = watchlist.model_copy(update={"entries": updated_entries})
        self.store.save_watchlist(watchlist)
        return watchlist

    def close(self, watchlist_id: str, *, note: str = "") -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        notes = list(watchlist.notes)
        if note.strip():
            notes.append(f"{timestamp} {note.strip()}")
        watchlist = watchlist.model_copy(
            update={"status": "closed", "closed_at": timestamp, "notes": notes}
        )
        self.store.save_watchlist(watchlist)
        return watchlist

    def snapshot(self, watchlist_id: str) -> Watchlist:
        watchlist = self._require(watchlist_id)
        return watchlist.model_copy()

    def diff(self, before: Watchlist, after: Watchlist) -> WatchlistDiff:
        before_map = {entry.symbol: entry for entry in before.entries}
        after_map = {entry.symbol: entry for entry in after.entries}
        added = sorted(after_map.keys() - before_map.keys())
        dropped = sorted(before_map.keys() - after_map.keys())
        grade_changes: dict[str, dict[str, str]] = {}
        for symbol in before_map.keys() & after_map.keys():
            old = before_map[symbol].last_grade
            new = after_map[symbol].last_grade
            if old != new:
                grade_changes[symbol] = {"from": old, "to": new}
        return WatchlistDiff(
            watchlist_id=after.watchlist_id,
            from_timestamp=before.created_at,
            to_timestamp=now_iso(),
            added_symbols=added,
            dropped_symbols=dropped,
            grade_changes=grade_changes,
        )

    def _require(self, watchlist_id: str) -> Watchlist:
        watchlist = self.store.get_watchlist(watchlist_id)
        if watchlist is None:
            raise KeyError(f"watchlist not found: {watchlist_id}")
        return watchlist
