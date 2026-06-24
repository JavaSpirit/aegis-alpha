from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aegis_alpha.adapters.factory import create_market_data_adapter
from aegis_alpha.adapters.jvquant import parsers as P
from aegis_alpha.config import load_project_env
from aegis_alpha.symbols import normalize_symbol


TURNOVER_QUERIES = [
    "成交额大于30亿,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
    "创业板,成交额大于30亿,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
]


def _env_symbols(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    for line in env_path.read_text().splitlines():
        if line.startswith("JVQUANT_SUBSCRIBE_SYMBOLS="):
            return [normalize_symbol(item) for item in line.split("=", 1)[1].split(",") if item.strip()]
    return []


def _write_env_key(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    rendered = f"{key}={value}"
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            output.append(rendered)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(rendered)
    env_path.write_text("\n".join(output).rstrip() + "\n")


def _merge_symbols(*groups: list[str], cap: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            symbol = normalize_symbol(raw)
            if not symbol or symbol in seen:
                continue
            merged.append(symbol)
            seen.add(symbol)
            if len(merged) >= cap:
                return merged
    return merged


def _limitup_symbols(adapter: Any, cap: int) -> list[str]:
    symbols: list[str] = []
    for item in adapter.get_limitup_pool():
        symbol = normalize_symbol(getattr(item, "symbol", ""))
        if symbol:
            symbols.append(symbol)
        if len(symbols) >= cap:
            break
    return symbols


def _turnover_symbols(adapter: Any, cap: int) -> list[str]:
    symbols: list[str] = []
    for query in TURNOVER_QUERIES:
        payload = adapter._query(query, sort_key="成交额")
        for row in P._query_rows(payload):
            symbol = normalize_symbol(P._symbol_from_row(row))
            if symbol:
                symbols.append(symbol)
            if len(symbols) >= cap:
                return symbols
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand JVQUANT_SUBSCRIBE_SYMBOLS with current live-provider active symbols.")
    parser.add_argument("--env-path", type=Path, default=Path(".env.local"))
    parser.add_argument("--cap", type=int, default=160)
    parser.add_argument("--limitup-cap", type=int, default=100)
    parser.add_argument("--turnover-cap", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_project_env()
    adapter = create_market_data_adapter()
    existing = _env_symbols(args.env_path)
    limitup = _limitup_symbols(adapter, args.limitup_cap)
    turnover = _turnover_symbols(adapter, args.turnover_cap)
    symbols = _merge_symbols(existing, turnover, limitup, cap=max(1, int(args.cap)))

    if not args.dry_run:
        _write_env_key(args.env_path, "JVQUANT_SUBSCRIBE_SYMBOLS", ",".join(symbols))

    print(
        json.dumps(
            {
                "env_path": str(args.env_path),
                "dry_run": args.dry_run,
                "cap": args.cap,
                "existing_count": len(existing),
                "turnover_count": len(set(turnover)),
                "limitup_count": len(set(limitup)),
                "merged_count": len(symbols),
                "new_count": len([symbol for symbol in symbols if symbol not in set(existing)]),
                "symbols": symbols,
                "notes": [
                    "This is a live-provider active-symbol expansion for realtime observation.",
                    "It does not change strategy scoring or agent selection rules.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
