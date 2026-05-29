from __future__ import annotations

import argparse
import json
from pathlib import Path

from aegis_alpha.replay import run_orderbook_replay_fixture
from aegis_alpha.storage import AegisAlphaStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a synthetic second-board orderbook scenario.")
    parser.add_argument("--symbol", default="TEST2B")
    parser.add_argument("--write-store", action="store_true", help="Persist the synthetic snapshot and events.")
    parser.add_argument("--db-path", type=Path)
    args = parser.parse_args()

    snapshot, events = run_orderbook_replay_fixture(symbol=args.symbol)
    persisted = False
    if args.write_store:
        store = AegisAlphaStore(args.db_path)
        store.save_signal_snapshot(snapshot)
        store.save_market_events(events)
        persisted = True

    print(
        json.dumps(
            {
                "scenario": "offline_second_board_orderbook_replay",
                "persisted": persisted,
                "snapshot": snapshot.model_dump(),
                "events": [event.model_dump() for event in events],
                "agent_readiness": {
                    "usable_for_agent": snapshot.freshness_status == "fresh",
                    "reason": (
                        "Synthetic replay validates the local signal/event pipeline. "
                        "It is not live market data and must not be used as a trading signal."
                    ),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
