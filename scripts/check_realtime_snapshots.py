from __future__ import annotations

import argparse
import json
from pathlib import Path

from aegis_alpha.config import load_project_env
from aegis_alpha.agent_context import signal_snapshot_agent_context
from aegis_alpha.storage import AegisAlphaStore, default_db_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect latest local realtime signal snapshots.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to latest stored symbols.")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    load_project_env()
    db_path = args.db_path or default_db_path()
    store = AegisAlphaStore(db_path)
    symbols = [item.strip().upper().split(".", 1)[0] for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        symbols = latest_symbols(db_path, args.limit)

    snapshots = []
    for symbol in symbols:
        snapshot = store.latest_signal_snapshot(symbol)
        if snapshot is None:
            snapshots.append(
                {
                    "symbol": symbol,
                    "data_mode": "unavailable",
                    "status": "Data source unavailable",
                }
            )
            continue
        snapshots.append(
            {
                "symbol": snapshot.symbol,
                "name": snapshot.name,
                "price": snapshot.price,
                "change_pct": snapshot.change_pct,
                "speed_1m_pct": snapshot.speed_1m_pct,
                "speed_3m_pct": snapshot.speed_3m_pct,
                "speed_5m_pct": snapshot.speed_5m_pct,
                "speed_10m_pct": snapshot.speed_10m_pct,
                "big_order_net_inflow_cny": snapshot.big_order_net_inflow_cny,
                "big_order_net_inflow_ratio": snapshot.big_order_net_inflow_ratio,
                "orderbook_quality_score": snapshot.orderbook_quality_score,
                "ask_pressure_score": snapshot.ask_pressure_score,
                "sell_wall_amount_cny": snapshot.sell_wall_amount_cny,
                "seal_amount_cny": snapshot.seal_amount_cny,
                "seal_decay_pct": snapshot.seal_decay_pct,
                "data_timestamp": snapshot.data_timestamp,
                "provider_timestamp": snapshot.provider_timestamp,
                "received_at": snapshot.received_at,
                "freshness_status": snapshot.freshness_status,
                "usable_for_agent": snapshot.freshness_status == "fresh",
                "notes": snapshot.notes,
            }
        )

    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "agent_context": signal_snapshot_agent_context(),
                "snapshots": snapshots,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def latest_symbols(db_path: Path, limit: int) -> list[str]:
    import sqlite3

    safe_limit = max(1, min(int(limit or 20), 200))
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, MAX(id) AS latest_id
            FROM signal_snapshots
            GROUP BY symbol
            ORDER BY latest_id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [str(row[0]) for row in rows]


if __name__ == "__main__":
    raise SystemExit(main())
