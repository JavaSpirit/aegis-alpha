from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import SealTimelineEvent
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_record_first_seal_then_break_then_reseal(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))

    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00", seal_amount_cny=120_000_000))
    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="break", occurred_at="2026-05-31T10:15:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="reseal", occurred_at="2026-05-31T10:42:00+08:00", seal_amount_cny=80_000_000))

    timeline = tracker.get_timeline("002230.SZ", "2026-05-31")

    assert [event.kind for event in timeline.events] == ["first_seal", "break", "reseal"]
    assert timeline.break_count == 1
    assert timeline.reseal_count == 1
    assert timeline.final_status == "reopened"


def test_final_break_marks_status_broken(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T14:55:00+08:00"))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "broken"


def test_no_break_means_sealed(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "sealed"
    assert timeline.break_count == 0


def test_empty_timeline_status_unknown(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "unknown"
    assert not timeline.events
