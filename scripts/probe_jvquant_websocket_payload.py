from __future__ import annotations

import argparse
import json
import time
from collections import Counter

from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient, summarize_raw_ab_payload
from aegis_alpha.config import load_project_env


def merge_summary(target: dict, update: dict) -> None:
    target["message_count"] += 1
    target["row_count"] += int(update.get("row_count") or 0)
    for level, level_update in (update.get("levels") or {}).items():
        level_summary = target["levels"].setdefault(
            level,
            {
                "row_count": 0,
                "max_piece_count": 0,
                "latest_field_count_distribution": Counter(),
            },
        )
        level_summary["row_count"] += int(level_update.get("row_count") or 0)
        level_summary["max_piece_count"] = max(
            level_summary["max_piece_count"],
            int(level_update.get("max_piece_count") or 0),
        )
        level_summary["latest_field_count_distribution"].update(
            int(value) for value in level_update.get("latest_field_counts", [])
        )
    for sample in update.get("samples") or []:
        if len(target["samples"]) < target["max_samples"]:
            target["samples"].append(sample)


def serializable_summary(summary: dict) -> dict:
    return {
        "message_count": summary["message_count"],
        "row_count": summary["row_count"],
        "levels": {
            level: {
                "row_count": item["row_count"],
                "max_piece_count": item["max_piece_count"],
                "latest_field_count_distribution": dict(sorted(item["latest_field_count_distribution"].items())),
            }
            for level, item in sorted(summary["levels"].items())
        },
        "samples": summary["samples"],
        "note": (
            "This probe summarizes raw jvQuant WebSocket payload shape only. "
            "It does not print tokens and does not expose raw payloads unless --include-fields is used."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe jvQuant WebSocket raw payload field counts.")
    parser.add_argument("--symbols", default="600519", help="Comma-separated symbols.")
    parser.add_argument("--levels", default="lv2", help="Comma-separated levels.")
    parser.add_argument("--duration", type=float, default=10.0, help="Seconds to sample.")
    parser.add_argument("--max-samples", type=int, default=10, help="Maximum summarized sample rows.")
    parser.add_argument("--include-fields", action="store_true", help="Include latest raw fields in samples.")
    args = parser.parse_args()

    load_project_env()
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    levels = [item.strip() for item in args.levels.split(",") if item.strip()]
    summary = {
        "message_count": 0,
        "row_count": 0,
        "levels": {},
        "samples": [],
        "max_samples": max(0, args.max_samples),
    }

    def handle_raw(text: str) -> None:
        merge_summary(
            summary,
            summarize_raw_ab_payload(
                text,
                max_rows=max(1, args.max_samples),
                include_samples=args.include_fields,
            ),
        )

    client = JvQuantRealtimeClient(raw_data_handle=handle_raw)
    status = client.subscribe(symbols, levels)
    time.sleep(max(0.0, args.duration))
    final_status = client.disconnect()
    payload = serializable_summary(summary)
    payload["initial_status"] = status.model_dump()
    payload["final_status"] = final_status.model_dump()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
