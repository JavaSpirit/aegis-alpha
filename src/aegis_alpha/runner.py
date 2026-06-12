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

from aegis_alpha.adapters.factory import create_market_data_adapter
from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient
from aegis_alpha.clock import SH_TZ, now_dt, now_iso
from aegis_alpha.config import load_project_env
from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
from aegis_alpha.extensions.sector_events import (
    LeaderBreakInputs,
    SectorRotationInputs,
    detect_sector_rotation,
    detect_theme_leader_break_board,
)
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


# ---------------------------------------------------------------------------
# Monitor windows — configurable [start, end) HH:MM slices for buy-point gate
# ---------------------------------------------------------------------------

DEFAULT_MONITOR_WINDOWS: list[dict[str, str]] = [
    {"name": "open_drive", "start": "09:30", "end": "09:50"},
    {"name": "late_morning", "start": "11:10", "end": "11:30"},
]


def _hhmm_to_minutes(hhmm: str) -> int | None:
    """Parse 'HH:MM' to integer minutes since midnight.  Returns None on any parse error."""
    parts = hhmm.split(":")
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def monitor_windows_from_config(config: dict) -> list[dict[str, str]]:
    """Return configured monitor_windows, or DEFAULT_MONITOR_WINDOWS if absent/empty.

    Each item must be a dict with str keys 'name', 'start', and 'end'.
    Malformed items (missing any of those keys) are silently skipped.
    If the resulting validated list is empty, falls back to DEFAULT_MONITOR_WINDOWS.
    """
    raw = config.get("monitor_windows")
    if not raw:
        return list(DEFAULT_MONITOR_WINDOWS)

    valid: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        start = item.get("start")
        end = item.get("end")
        if name is None or start is None or end is None:
            continue
        valid.append({"name": str(name), "start": str(start), "end": str(end)})

    return valid if valid else list(DEFAULT_MONITOR_WINDOWS)


def is_in_monitor_window(now_hhmm: str, windows: list[dict[str, str]]) -> str | None:
    """Return the name of the first window whose [start, end) range contains now_hhmm, else None.

    Args:
        now_hhmm: Current local time as a zero-padded 'HH:MM' string (24-hour clock).
                  The runner passes the current Shanghai time here; this function is pure
                  and NEVER calls datetime.now() internally.
        windows:  List of window dicts, each with 'name', 'start', 'end' keys (HH:MM strings).

    Returns:
        The window name (str) when now_hhmm falls in [start, end), None otherwise.

    Boundary convention:
        start is INCLUSIVE, end is EXCLUSIVE.
        e.g. window "09:30"–"09:50": "09:30" is inside, "09:50" is outside.

    Malformed now_hhmm (empty string, no colon, invalid digits, out-of-range hours/minutes)
    returns None without raising.  Malformed window entries are silently skipped.
    """
    now_min = _hhmm_to_minutes(now_hhmm)
    if now_min is None:
        return None

    for window in windows:
        start_min = _hhmm_to_minutes(str(window.get("start", "")))
        end_min = _hhmm_to_minutes(str(window.get("end", "")))
        if start_min is None or end_min is None:
            continue
        if start_min <= now_min < end_min:
            return str(window.get("name", ""))

    return None


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
        self._sector_events_adapter = None  # lazy-built on first _collect_sector_events

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
            try:
                self.detect_buypoints_in_window(symbols)
            except Exception:
                # Buy-point detection is advisory; never kill the runner cycle
                pass
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
        sector_events = self._collect_sector_events()
        events.extend(sector_events)
        if events:
            self.store.save_market_events(events)
            self._maybe_alert_from_events(events)
        self._last_persist_counts = {"snapshots": snapshot_count, "events": len(events)}

    def _collect_sector_events(self) -> list[MarketEvent]:
        """Best-effort: fetch ThemeLeader snapshot and run sector-event detectors.

        Each step has its own try/except so partial results survive a failing
        detector. Failures are still swallowed — sector events are advisory and
        runner liveness must not depend on them.
        """
        from datetime import date as _date

        try:
            if self._sector_events_adapter is None:
                self._sector_events_adapter = create_market_data_adapter()
            adapter = self._sector_events_adapter
            trading_day = _date.today().isoformat()
            leaders = adapter.get_theme_leaders(theme="", trading_day=trading_day)
        except Exception:
            return []
        if not leaders:
            return []

        events: list[MarketEvent] = []
        try:
            events.extend(
                detect_theme_leader_break_board(
                    LeaderBreakInputs(leaders=leaders, trading_day=trading_day)
                )
            )
        except Exception:
            pass
        try:
            events.extend(
                detect_sector_rotation(
                    SectorRotationInputs(leaders=leaders, trading_day=trading_day)
                )
            )
        except Exception:
            pass
        return events

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
            "THEME_LEADER_BREAK_BOARD",
            "SECTOR_ROTATION",
            "MARKET_BOTTOM_REVERSAL",
        }
        for event in events:
            if event.event_type not in critical_types:
                continue
            critical_severity_types = {
                "SEAL_ORDER_DECAY",
                "THEME_LEADER_BREAK_BOARD",
                "MARKET_BOTTOM_REVERSAL",
            }
            severity = (
                "critical" if event.event_type in critical_severity_types else "warning"
            )
            alert = alert_store.create(
                title=f"{event.event_type} {event.symbol}",
                body="; ".join(event.evidence)[:512],
                severity=severity,
                event_id=event.event_id,
                symbol=event.symbol,
                theme=event.theme,
            )
            notify_macos(alert)

    def detect_buypoints_in_window(self, symbols: list[str]) -> list:
        """Window-gated live buy-point replay — runs only inside the configured monitor windows.

        Reads rolling tick data from the buffer, aggregates into minute bars, drives the
        buy-point state machine (Phase 4), and emits a paper alert for each fired signal.

        This method is read-only with respect to config and orders.  It ONLY writes
        AgentAlert records and fires desktop notifications.  It never places orders.

        Returns:
            List of IntradayBuyPointSignal objects for signals that fired this call
            (may be empty if outside the window, insufficient data, or no pattern).
        """
        from aegis_alpha.measurements.buypoint_replay import replay_buypoint
        from aegis_alpha.measurements.minute_bars import rolling_points_to_minute_bars
        from aegis_alpha.models import MinuteReplaySnapshot
        from aegis_alpha.alerts.notifier import notify_macos
        from aegis_alpha.alerts.store import AlertStore

        now_hhmm = now_dt().strftime("%H:%M")
        windows = monitor_windows_from_config(self.config)
        window_name = is_in_monitor_window(now_hhmm, windows)
        if window_name is None:
            return []

        trading_day = now_dt().date().isoformat()
        timestamp = now_iso()
        alert_store = AlertStore(self.store)

        # Lazily build / reuse the market data adapter (same pattern as _collect_sector_events)
        if self._sector_events_adapter is None:
            try:
                self._sector_events_adapter = create_market_data_adapter()
            except Exception:
                pass

        # Try to load all second-board candidates once (best-effort)
        candidates: list = []
        if self._sector_events_adapter is not None:
            try:
                candidates = self._sector_events_adapter.get_second_board_candidates()
            except Exception:
                candidates = []

        fired_signals: list = []

        for symbol in symbols:
            try:
                points = self.buffer.rolling_points(symbol)
                # Need baseline_window=3 + at least 1 eval bar = 4 bars minimum
                bars = rolling_points_to_minute_bars(points)  # turnover_is_cumulative=True (default)
                if len(bars) < 4:
                    continue

                # ------------------------------------------------------------------
                # Resolve previous_high — fact-first with opening-window fallback
                # ------------------------------------------------------------------
                prev_high: float = 0.0
                prev_high_source: str = ""

                # Normalize symbol for lookup: strip, upper, drop exchange suffix
                sym_key = symbol.strip().upper().split(".", 1)[0]
                for candidate in candidates:
                    cand_key = str(candidate.symbol).strip().upper().split(".", 1)[0]
                    if cand_key == sym_key and candidate.previous_high_price > 0:
                        prev_high = candidate.previous_high_price
                        prev_high_source = "fact"
                        break

                if prev_high <= 0:
                    # Fallback: use the high over the first baseline_window bars
                    baseline_window = 3
                    opening_bars = bars[:baseline_window]
                    if opening_bars:
                        prev_high = max(b.last_price for b in opening_bars)
                        prev_high_source = "opening_window_fallback"

                if prev_high <= 0:
                    # Cannot define a breakout level — skip
                    continue

                snap = MinuteReplaySnapshot(
                    symbol=symbol,
                    trading_day=trading_day,
                    timestamp=timestamp,
                    bars=bars,
                )
                signals = replay_buypoint(snap, previous_high=prev_high)

                for signal in signals:
                    if signal.state != "buy_point_alert":
                        continue
                    fired_signals.append(signal)

                    # Stable dedup key: same symbol + same triggered bar time → no re-alert
                    event_id = f"buypoint:{symbol}:{signal.triggered_at}"
                    alert = alert_store.create(
                        title=f"BUYPOINT_ALERT {symbol}",
                        body=("; ".join(signal.evidence)[:480] + f" | previous_high_source={prev_high_source}"),
                        severity="warning",
                        event_id=event_id,
                        symbol=symbol,
                    )
                    notify_macos(alert)

            except Exception:
                # Buy-point detection is advisory; runner liveness must not depend on it
                pass

        return fired_signals

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
