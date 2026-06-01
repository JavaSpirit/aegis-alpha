from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aegis_alpha.runner import (
    AegisAlphaRunner,
    is_trading_session_active,
    load_runner_config,
    reconnect_delay_seconds,
    status_payload,
    subscription_levels,
    subscription_symbols,
)


def test_runner_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("JVQUANT_SUBSCRIBE_SYMBOLS", raising=False)
    config = load_runner_config()

    assert config["provider"] == "jvQuant"
    assert subscription_symbols(config)
    assert subscription_levels(config) == ["lv1", "lv2", "lv10"]


def test_runner_session_detection() -> None:
    config = load_runner_config()
    tz = ZoneInfo("Asia/Shanghai")

    assert is_trading_session_active(config, datetime(2026, 5, 28, 9, 30, tzinfo=tz))
    assert not is_trading_session_active(config, datetime(2026, 5, 28, 12, 0, tzinfo=tz))


def test_runner_status_payload_when_missing(tmp_path) -> None:
    config_path = tmp_path / "runner.yaml"
    config_path.write_text(
        """
storage:
  status_path: missing-status.json
trading_sessions: []
""".strip()
    )

    payload = status_payload(str(config_path))

    assert payload["state"] == "STOPPED"
    assert payload["notes"]


def test_reconnect_delay_uses_exponential_backoff_with_jitter() -> None:
    config = {
        "reconnect_interval_seconds": 10,
        "reconnect_max_interval_seconds": 45,
        "reconnect_jitter_ratio": 0.2,
    }

    assert reconnect_delay_seconds(config, 0, jitter=0.0) == 10
    assert reconnect_delay_seconds(config, 1, jitter=0.0) == 20
    assert reconnect_delay_seconds(config, 2, jitter=0.1) == 44
    assert reconnect_delay_seconds(config, 3, jitter=0.0) == 45


def test_runner_persists_buffer_outputs(tmp_path) -> None:
    config_path = tmp_path / "runner.yaml"
    db_path = tmp_path / "runner.db"
    status_path = tmp_path / "runner_status.json"
    config_path.write_text(
        f"""
market: ab
loop_interval_seconds: 5
trading_sessions:
  - name: all_day
    start: "00:00"
    end: "23:59"
subscription:
  default_symbols: ["600000"]
  levels: ["lv1"]
storage:
  sqlite_path: "{db_path}"
  status_path: "{status_path}"
""".strip()
    )
    runner = AegisAlphaRunner(str(config_path), connect=False)
    runner.buffer.add_price("600000", "2026-05-28T09:30:00+08:00", 10.0, 100_000_000, change_pct=8.8)
    runner.buffer.add_price("600000", "2026-05-28T09:35:00+08:00", 10.4, 100_000_000, change_pct=9.4)
    runner.buffer.add_big_order_flow("600000", 50_000_000)

    runner.persist_buffer_outputs(["600000"])

    assert runner.store.signal_snapshot_count("600000") == 1
    assert runner.store.market_event_count() >= 1


def test_persist_buffer_outputs_appends_sector_events_when_leader_breaks(tmp_path, monkeypatch):
    """persist_buffer_outputs should fetch theme leaders and append
    THEME_LEADER_BREAK_BOARD events when a leader's status is 'broken'."""
    from unittest.mock import MagicMock
    from aegis_alpha.models import ThemeLeader
    from aegis_alpha.runner import AegisAlphaRunner

    config_path = tmp_path / "runner.yaml"
    db_path = tmp_path / "runner.db"
    config_path.write_text(
        f"""
market: ab
loop_interval_seconds: 5
trading_sessions:
  - name: all_day
    start: "00:00"
    end: "23:59"
subscription:
  default_symbols: ["600000"]
  levels: ["lv1"]
storage:
  sqlite_path: "{db_path}"
  status_path: "{tmp_path / 'runner_status.json'}"
""".strip()
    )

    # Ensure the runner builds; we then patch internals.
    runner = AegisAlphaRunner(config_path=str(config_path), connect=False)

    # No buffer snapshots → detector contributes 0 events.
    # We just need persist_buffer_outputs to call the sector-event detector.

    broken_leader = ThemeLeader(
        theme="AI", trading_day="2026-06-01",
        leader_symbol="600519", leader_name="L",
        leader_consecutive_boards=3,
        leader_first_limit_up_time="09:30:00",
        leader_seal_amount_cny=200_000_000.0,
        leader_status="broken",
        co_leader_symbols=[],
        member_count=4,
    )

    fake_adapter = MagicMock()
    fake_adapter.get_theme_leaders = MagicMock(return_value=[broken_leader])

    monkeypatch.setattr(
        "aegis_alpha.runner.create_market_data_adapter",
        lambda: fake_adapter,
        raising=False,
    )

    captured: list = []
    runner._maybe_alert_from_events = lambda events: captured.extend(events)  # type: ignore[assignment]

    runner.persist_buffer_outputs(["600000"])

    types = {e.event_type for e in captured}
    assert "THEME_LEADER_BREAK_BOARD" in types
