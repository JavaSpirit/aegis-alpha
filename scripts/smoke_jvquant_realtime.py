from __future__ import annotations

import argparse
import json
import time

from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient, subscription_codes
from aegis_alpha.config import load_project_env
from aegis_alpha.events import EventDetector
from aegis_alpha.storage import AegisAlphaStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only jvQuant WebSocket smoke helper.")
    parser.add_argument("--symbols", default="600519,000001", help="Comma-separated symbols.")
    parser.add_argument("--levels", default="lv1,lv2,lv10", help="Comma-separated levels: lv1,lv2,lv10.")
    parser.add_argument("--connect", action="store_true", help="Actually connect and subscribe.")
    parser.add_argument("--duration", type=float, default=5.0, help="Seconds to wait after subscribing.")
    args = parser.parse_args()

    load_project_env()
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    levels = [item.strip() for item in args.levels.split(",") if item.strip()]
    client = JvQuantRealtimeClient()

    if not args.connect:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "subscription_codes": subscription_codes(symbols, levels),
                    "status": client.status().model_dump(),
                    "note": "Rerun with --connect to open a read-only WebSocket subscription.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    status = client.subscribe(symbols, levels)
    time.sleep(max(0.0, args.duration))
    store = AegisAlphaStore()
    detector = EventDetector()
    snapshots = []
    events = []
    for symbol in symbols:
        snapshot = client.buffer.latest_snapshot(symbol)
        if snapshot.price <= 0:
            continue
        store.save_signal_snapshot(snapshot)
        snapshots.append(snapshot.model_dump())
        detected = detector.detect_from_snapshot(snapshot)
        store.save_market_events(detected)
        events.extend(event.model_dump() for event in detected)
    final_status = client.disconnect()
    print(
        json.dumps(
            {
                "mode": "connected",
                "initial_status": status.model_dump(),
                "final_status": final_status.model_dump(),
                "snapshot_count": len(snapshots),
                "event_count": len(events),
                "snapshots": snapshots,
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
