from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aegis_alpha.runner import (
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
