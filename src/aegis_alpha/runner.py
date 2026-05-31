from __future__ import annotations

import argparse
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as day_time
from pathlib import Path

import yaml

from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient
from aegis_alpha.clock import SH_TZ, now_iso
from aegis_alpha.config import load_project_env
from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
from aegis_alpha.models import MarketEvent, RunnerStatus
from aegis_alpha.storage import AegisAlphaStore, read_runner_status, write_runner_status


@dataclass(frozen=True)
class TradingSession:
    name: str
    start: day_time
    end: day_time

    def contains(self, value: day_time) -> bool:
        return self.start <= value <= self.end


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_runner_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else project_root() / "config" / "runner.yaml"
    payload = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    return payload or {}


def parse_time(value: str) -> day_time:
    return datetime.strptime(value, "%H:%M").time()


def trading_sessions(config: dict) -> list[TradingSession]:
    sessions = []
    for raw in config.get("trading_sessions", []):
        sessions.append(
            TradingSession(
                name=str(raw.get("name") or "session"),
                start=parse_time(str(raw["start"])),
                end=parse_time(str(raw["end"])),
            )
        )
    return sessions


def is_trading_session_active(config: dict, now: datetime | None = None) -> bool:
    current = now or datetime.now(SH_TZ)
    return any(session.contains(current.time()) for session in trading_sessions(config))


def subscription_symbols(config: dict) -> list[str]:
    subscription = config.get("subscription", {})
    env_key = str(subscription.get("symbols_env") or "JVQUANT_SUBSCRIBE_SYMBOLS")
    raw = os.environ.get(env_key, "")
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    if not symbols:
        symbols = [str(item).strip() for item in subscription.get("default_symbols", []) if str(item).strip()]
    return symbols


def subscription_levels(config: dict) -> list[str]:
    return [str(item).strip().lower() for item in config.get("subscription", {}).get("levels", ["lv1", "lv2", "lv10"])]


def reconnect_delay_seconds(config: dict, failure_count: int, *, jitter: float | None = None) -> float:
    base = max(1.0, float(config.get("reconnect_interval_seconds") or 30))
    cap = max(base, float(config.get("reconnect_max_interval_seconds") or 300))
    exponent = max(0, min(int(failure_count), 10))
    delay = min(cap, base * (2 ** exponent))
    jitter_ratio = max(0.0, min(1.0, float(config.get("reconnect_jitter_ratio") or 0.20)))
    jitter_value = random.uniform(0.0, jitter_ratio) if jitter is None else max(0.0, min(jitter_ratio, jitter))
    return round(delay * (1.0 + jitter_value), 3)


class AegisAlphaRunner:
    def __init__(self, config_path: str | Path | None = None, *, connect: bool = True) -> None:
        load_project_env()
        self.config = load_runner_config(config_path)
        self.connect_enabled = connect
        self.started_at = now_iso()
        self.stop_requested = False
        self.buffer = SignalWindowBuffer()
        self.store = AegisAlphaStore(self.config.get("storage", {}).get("sqlite_path"))
        self.client = JvQuantRealtimeClient(
            token=os.environ.get("JVQUANT_TOKEN", ""),
            market=str(self.config.get("market") or os.environ.get("JVQUANT_MARKET", "ab")),
            buffer=self.buffer,
        )
        self.status_path = self.config.get("storage", {}).get("status_path")
        self.detector = EventDetector(load_event_scoring_config())
        self._last_persist_counts: dict[str, int] = {"snapshots": 0, "events": 0}

    def request_stop(self, *_args: object) -> None:
        self.stop_requested = True
        self.write_status("STOPPING", next_action="disconnect")

    def write_status(self, state: str, *, next_action: str = "", last_error: str = "") -> RunnerStatus:
        connection = self.client.status()
        status = RunnerStatus(
            state=state,  # type: ignore[arg-type]
            pid=os.getpid(),
            started_at=self.started_at,
            updated_at=now_iso(),
            trading_session_active=is_trading_session_active(self.config),
            next_action=next_action,
            provider=connection.provider,
            subscribed=connection.subscribed,
            last_event_at=connection.last_message_at,
            last_error=last_error or connection.last_error,
            connection=connection,
            notes=[
                "launchd may keep this process alive; Aegis Alpha only opens market subscriptions during configured trading sessions.",
                "Runner does not call LLMs, place orders, or expose raw WebSocket messages.",
                f"last_persisted_snapshots={self._last_persist_counts['snapshots']}",
                f"last_persisted_events={self._last_persist_counts['events']}",
            ],
        )
        write_runner_status(status, self.status_path)
        return status

    def run_once(self) -> RunnerStatus:
        active = is_trading_session_active(self.config)
        if not active:
            self.client.disconnect()
            status = self.write_status("WAITING", next_action="wait_for_trading_session")
            self.store.save_provider_run(
                provider=status.provider,
                run_type="runner_cycle",
                status=status.state,
                started_at=self.started_at,
                ended_at=status.updated_at,
                payload=status.model_dump(),
            )
            return status

        if not self.connect_enabled:
            return self.write_status("DEGRADED", next_action="connect_disabled")

        try:
            symbols = subscription_symbols(self.config)
            levels = subscription_levels(self.config)
            connection = self.client.status()
            if not connection.connected:
                self.write_status("STARTING", next_action="connect_websocket")
                connection = self.client.subscribe(symbols, levels)
            self.persist_buffer_outputs(symbols)
            state = "RUNNING" if connection.connected and not connection.last_error else "DEGRADED"
            status = self.write_status(state, next_action="listen")
        except Exception as exc:
            status = self.write_status("DEGRADED", next_action="reconnect", last_error=type(exc).__name__)

        self.store.save_provider_run(
            provider=status.provider,
            run_type="runner_cycle",
            status=status.state,
            started_at=self.started_at,
            ended_at=status.updated_at,
            payload=status.model_dump(),
        )
        return status

    def persist_buffer_outputs(self, symbols: list[str]) -> None:
        events = []
        snapshot_count = 0
        for symbol in symbols:
            snapshot = self.buffer.latest_snapshot(symbol, received_at=now_iso())
            if snapshot.price <= 0:
                continue
            self.store.save_signal_snapshot(snapshot)
            snapshot_count += 1
            events.extend(self.detector.detect_from_snapshot(snapshot))
        if events:
            self.store.save_market_events(events)
            self._maybe_alert_from_events(events)
        self._last_persist_counts = {"snapshots": snapshot_count, "events": len(events)}

    def _maybe_alert_from_events(self, events: list[MarketEvent]) -> None:
        try:
            from aegis_alpha.alerts.notifier import notify_macos
            from aegis_alpha.alerts.store import AlertStore
        except Exception:
            return
        alert_store = AlertStore(self.store)
        critical_types = {
            "SEAL_ORDER_DECAY",
            "BIG_ORDER_INFLOW_SPIKE",
            "THEME_DIVERGENCE",
        }
        for event in events:
            if event.event_type not in critical_types:
                continue
            severity = "critical" if event.event_type == "SEAL_ORDER_DECAY" else "warning"
            alert = alert_store.create(
                title=f"{event.event_type} {event.symbol}",
                body="; ".join(event.evidence)[:512],
                severity=severity,
                event_id=event.event_id,
                symbol=event.symbol,
                theme=event.theme,
            )
            notify_macos(alert)

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self.write_status("STARTING", next_action="initial_cycle")
        interval = max(5, int(self.config.get("loop_interval_seconds") or 15))
        failure_count = 0
        while not self.stop_requested:
            status = self.run_once()
            if status.state == "DEGRADED":
                interval = reconnect_delay_seconds(self.config, failure_count)
                failure_count += 1
            else:
                interval = max(5, int(self.config.get("loop_interval_seconds") or 15))
                failure_count = 0
            time.sleep(interval)
        self.client.disconnect()
        self.write_status("STOPPED", next_action="stopped")


def status_payload(config_path: str | None = None) -> dict:
    config = load_runner_config(config_path)
    status = read_runner_status(config.get("storage", {}).get("status_path"))
    return status.model_dump() if status else {
        "state": "STOPPED",
        "updated_at": now_iso(),
        "notes": ["No runner status file found."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aegis Alpha launchd-friendly market data runner.")
    parser.add_argument("--config", default="", help="Path to runner YAML config.")
    parser.add_argument("--once", action="store_true", help="Run one lifecycle cycle and exit.")
    parser.add_argument("--status", action="store_true", help="Print current runner status and exit.")
    parser.add_argument("--no-connect", action="store_true", help="Do not open WebSocket connections.")
    args = parser.parse_args(argv)

    if args.status:
        import json

        print(json.dumps(status_payload(args.config or None), ensure_ascii=False, indent=2))
        return 0

    runner = AegisAlphaRunner(args.config or None, connect=not args.no_connect)
    if args.once:
        status = runner.run_once()
        print(status.model_dump_json(indent=2))
        return 0 if status.state in {"WAITING", "RUNNING"} else 1
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
