from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import SealTimelineEvent, ThemeLeader
from aegis_alpha.seal_timeline.divergence import detect_theme_divergence
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_leader_break_with_followers_alive_emits_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:30:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:00:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F2", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:30:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", co_leader_symbols=["F1", "F2"], member_count=3)

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert len(events) == 1
    assert events[0].event_type == "THEME_DIVERGENCE"
    assert events[0].theme == "AI"
    assert "LDR" in events[0].evidence[0]


def test_leader_alive_no_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", member_count=3)

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert events == []


def test_leader_break_with_no_alive_followers_no_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:30:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", co_leader_symbols=["F1"], member_count=2)
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:00:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:50:00+08:00"))

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert events == []
