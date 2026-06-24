from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aegis_alpha.config import load_project_env
from aegis_alpha.runner import status_payload


def main() -> int:
    load_project_env()

    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    today = now.date().isoformat()
    session_start = f"{today}T13:00:00+08:00"
    db_path = Path("data/aegis_alpha.db")

    with sqlite3.connect(db_path) as conn:
        snapshot_count = conn.execute(
            "select count(*) from signal_snapshots where received_at >= ?",
            (session_start,),
        ).fetchone()[0]
        latest_snapshot = conn.execute(
            """
            select symbol, received_at, provider_timestamp, freshness_status
            from signal_snapshots
            where received_at >= ?
            order by received_at desc
            limit 1
            """,
            (session_start,),
        ).fetchone()
        provider_runs = conn.execute(
            """
            select status, json_extract(payload_json, '$.next_action'), json_extract(payload_json, '$.last_error'), count(*)
            from provider_runs
            where ended_at >= ?
            group by status, json_extract(payload_json, '$.next_action'), json_extract(payload_json, '$.last_error')
            order by status
            """,
            (session_start,),
        ).fetchall()

    status = status_payload("config/runner.yaml")
    connection = status.get("connection") or {}

    print(
        json.dumps(
            {
                "checked_at": now.isoformat(timespec="seconds"),
                "session_start": session_start,
                "runner_state": status.get("state"),
                "runner_next_action": status.get("next_action"),
                "runner_last_error": status.get("last_error"),
                "provider": status.get("provider"),
                "connection_connected": connection.get("connected"),
                "connection_last_message_at": connection.get("last_message_at"),
                "connection_last_error": connection.get("last_error"),
                "snapshot_count_since_session_start": snapshot_count,
                "latest_snapshot_since_session_start": {
                    "symbol": latest_snapshot[0],
                    "received_at": latest_snapshot[1],
                    "provider_timestamp": latest_snapshot[2],
                    "freshness_status": latest_snapshot[3],
                }
                if latest_snapshot
                else None,
                "provider_runs_since_session_start": [
                    {
                        "status": row[0],
                        "next_action": row[1],
                        "last_error": row[2],
                        "count": row[3],
                    }
                    for row in provider_runs
                ],
                "verdict": (
                    "ok_live_snapshots_present"
                    if snapshot_count > 0 and connection.get("last_message_at")
                    else "not_ok_no_live_snapshots_or_messages"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
