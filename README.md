# Aegis Alpha

Aegis Alpha is a Hermes companion for A-share trading research and second-board watchlist assistance. It helps install or verify Hermes, then exposes read-only MCP tools for market sentiment gating, second-board candidate monitoring, theme analysis, and candidate explanation.

The MVP is intentionally conservative:

- No real trading.
- No broker credentials.
- No real Level-2 credentials.
- No buy or sell instructions.
- Mock market data only.
- Second-board radar first; automated trading later.

## What It Is

Aegis Alpha is designed as a safe capability pack for Hermes. It does not fork or modify Hermes; it adapts to Hermes through documented MCP configuration.

```text
Hermes Agent
  -> Aegis Alpha MCP Server
  -> Market Data Adapters
  -> Research, watchlist, replay, and future risk controls
```

The first version only provides read-only tools. Future versions can add real data adapters, paper trading, and tightly controlled order proposals.

The first product focus is a second-board radar:

```text
Market sentiment gate
  -> yesterday limit-up pool
  -> second-board candidates
  -> 5-minute speed and big-order inflow
  -> theme co-movement
  -> historical limit-up and gap-up stats
  -> watchlist grade and risk explanation
```

## Requirements

- Python 3.11+
- Hermes Agent, or another MCP-compatible agent runtime

## Install Aegis Alpha

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

If your package manager does not support optional extras yet, install the base package first:

```bash
python -m pip install -e .
```

## Install Or Verify Hermes

Aegis Alpha includes a helper that checks for Hermes and can run the official Hermes installer when explicitly requested:

```bash
scripts/install_hermes.sh
scripts/install_hermes.sh --run
```

The helper defaults to dry-run mode. It does not modify Hermes, fork Hermes, or vendor Hermes code. See [docs/HERMES.md](docs/HERMES.md) for the integration details.

## Run The MCP Server

```bash
aegis-alpha-mcp
```

Hermes can be configured to launch this command as a local MCP server. The server currently uses deterministic mock data, so it is safe to run without market-data credentials.

## MCP Tools

The MVP exposes these read-only tools:

- `get_market_snapshot`
- `get_market_sentiment_gate`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_realtime_snapshot`
- `get_stock_history_limitup_stats`
- `get_theme_strength`
- `get_second_board_candidates`
- `explain_candidate`
- `explain_second_board_candidate`

`explain_candidate(symbol)` returns structured watchlist output:

```json
{
  "grade": "B",
  "observations": [],
  "risks": [],
  "trigger_conditions": [],
  "avoid_conditions": [],
  "data_timestamp": "2026-05-24T09:30:00+08:00"
}
```

The output is for research and watchlist use only. It is not investment advice and not an order instruction.

`explain_second_board_candidate(symbol)` focuses on second-board logic: market sentiment gate, 5-minute speed, big-order net inflow ratio, same-theme co-movement, orderbook quality, and three-year historical limit-up/gap-up placeholders.

## Development Checks

```bash
python -m compileall src scripts tests
PYTHONPATH=src python scripts/smoke_check.py
```

## Security Boundary

Do not commit real secrets, API keys, broker tokens, Level-2 credentials, or account identifiers. Use `.env.example` as a local template only.

Real trading tools are intentionally absent from this MVP. Future trading actions must be added behind explicit risk controls, audit logs, and human confirmation.

## Packaging Direction

The MVP ships as a Python package with a console command because this is easiest to inspect and debug while MCP contracts are still evolving. Once stable, the same server can be packaged as a Docker image or standalone binary.
