from __future__ import annotations

import argparse
import json
import logging
import signal
from pathlib import Path
from typing import Any

import requests


class SmokeTimeout(Exception):
    pass


def _alarm_handler(signum: int, frame: object) -> None:
    raise SmokeTimeout("jvQuant smoke test timed out")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def summarize_payload(payload: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"response_type": type(payload).__name__}
    if not isinstance(payload, dict):
        return summary

    summary["top_level_keys"] = sorted(payload.keys())
    for key in ("code", "message", "msg", "cnt"):
        if key in payload:
            summary[key] = payload[key]

    data = payload.get("data")
    summary["data_type"] = type(data).__name__ if data is not None else None

    if isinstance(data, dict):
        summary["data_keys"] = sorted(data.keys())[:30]
        for key, value in data.items():
            if isinstance(value, list):
                summary[f"{key}_count"] = len(value)
                if value:
                    first = value[0]
                    if isinstance(first, dict):
                        summary[f"{key}_first_sample"] = {
                            sample_key: first[sample_key]
                            for sample_key in list(first.keys())[:8]
                        }
                    elif isinstance(first, list):
                        summary[f"{key}_first_sample"] = first[:12]
                    else:
                        summary[f"{key}_first_sample"] = first
            elif not isinstance(value, dict):
                summary[key] = value
    elif isinstance(data, list):
        summary["data_count"] = len(data)
        if data:
            first = data[0]
            summary["data_first_sample"] = first[:12] if isinstance(first, list) else first

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only jvQuant smoke test.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(args.timeout)

    real_get = requests.get

    def get_with_timeout(*request_args: Any, **request_kwargs: Any) -> requests.Response:
        request_kwargs.setdefault("timeout", min(args.timeout, 8))
        return real_get(*request_args, **request_kwargs)

    requests.get = get_with_timeout

    try:
        from jvQuant import sql_client

        env = load_env(Path(args.env_file))
        token = env.get("JVQUANT_TOKEN", "")
        if not token:
            raise ValueError("JVQUANT_TOKEN missing")

        client = sql_client.Construct(token=token, log_level=logging.ERROR)
        result = {
            "data_mode": "live_provider_smoke",
            "provider": "jvQuant",
            "symbol": args.symbol,
            "secrets_printed": False,
            "calls": {
                "kline_day_2": summarize_payload(
                    client.kline(args.symbol, "stock", "前复权", "day", 2)
                ),
                "level_queue": summarize_payload(client.level_queue(args.symbol)),
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "data_mode": "live_provider_smoke",
                    "provider": "jvQuant",
                    "symbol": args.symbol,
                    "secrets_printed": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
