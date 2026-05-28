from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aegis_alpha.runner import (
    AegisAlphaRunner,
    is_trading_session_active,
    load_runner_config,
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
