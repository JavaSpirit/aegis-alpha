from __future__ import annotations

from typing import Literal

from aegis_alpha.models import SealTimeline, SealTimelineEvent
from aegis_alpha.storage import AegisAlphaStore


class SealTimelineTracker:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def record(self, event: SealTimelineEvent) -> SealTimelineEvent:
        self.store.save_seal_timeline_event(event)
        return event

    def get_timeline(self, symbol: str, trading_day: str) -> SealTimeline:
        events = self.store.list_seal_timeline_events(symbol, trading_day)
        events_sorted = sorted(events, key=lambda item: item.occurred_at)
        break_count = sum(1 for event in events_sorted if event.kind in {"break", "final_break"})
        reseal_count = sum(1 for event in events_sorted if event.kind == "reseal")
        final_status = self._derive_final_status(events_sorted)
        return SealTimeline(
            symbol=symbol,
            trading_day=trading_day,
            events=events_sorted,
            final_status=final_status,
            break_count=break_count,
            reseal_count=reseal_count,
        )

    @staticmethod
    def _derive_final_status(events: list[SealTimelineEvent]) -> Literal["sealed", "broken", "reopened", "unknown"]:
        if not events:
            return "unknown"
        last = events[-1]
        if last.kind == "first_seal":
            return "sealed"
        if last.kind == "final_break":
            return "broken"
        if last.kind == "break":
            return "broken"
        if last.kind == "reseal":
            return "reopened"
        return "unknown"
