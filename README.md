# Aegis Alpha

Aegis Alpha is a Hermes companion for A-share trading research and second-board watchlist assistance. It helps install or verify Hermes, then exposes read-only MCP tools for market sentiment gating, second-board candidate monitoring, theme analysis, and candidate explanation.

The MVP is intentionally conservative:

- No real trading.
- No broker credentials.
- No real Level-2 credentials.
- No buy or sell instructions.
- Mock data by default; optional read-only jvQuant market data.
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

For a full local setup, including Python environment, Aegis Alpha, jvQuant, Hermes, skill, MCP config, and integration check:

```bash
scripts/install_all.sh
```

The reproducible Hermes template is stored in:

```text
.hermes/config/config.example.yaml
```

It contains provider, fallback, and Aegis Alpha MCP settings. Real keys stay in `.env.local` and `~/.hermes/.env`.

Preview the full setup without changing anything:

```bash
scripts/install_all.sh --dry-run
```

Hermes provider policy:

```text
primary: OpenRouter
fallback: DeepSeek direct deepseek-v4-pro
```

Provider setup docs: [docs/PROVIDERS.md](docs/PROVIDERS.md).

`scripts/install_all.sh` uses the project Hermes template and can sync `DEEPSEEK_API_KEY` and `OPENROUTER_API_KEY` from project `.env.local` into `~/.hermes/.env` without printing key values.

Manual Python-only setup:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install ".[dev]"
```

If your package manager does not support optional extras yet, install the base package first:

```bash
python -m pip install .
```

## Install jvQuant Market Data Dependency

The MVP runs on mock data by default. To prepare the read-only jvQuant adapter work, install the jvQuant package into the local environment:

```bash
scripts/install_jvquant.sh
```

Or install through the optional dependency group:

```bash
python -m pip install ".[jvquant]"
```

Then put local credentials in `.env.local`:

```bash
AEGIS_ALPHA_MARKET_DATA_PROVIDER=jvquant
JVQUANT_TOKEN=your-token
JVQUANT_MARKET=ab
AEGIS_ALPHA_REAL_TRADING_ENABLED=false
```

Do not commit `.env.local`.

Run a read-only jvQuant smoke test without printing secrets:

```bash
.venv/bin/python scripts/smoke_jvquant_readonly.py --symbol 600519
```

When `AEGIS_ALPHA_MARKET_DATA_PROVIDER=jvquant`, Hermes can access jvQuant-backed market and single-symbol data through Aegis Alpha MCP:

- `get_market_snapshot`
- `get_market_sentiment_gate`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_second_board_candidates_compact(limit)`
- `get_second_board_candidates`
- `get_second_board_candidate_data_quality(symbol)`
- `explain_second_board_candidate(symbol)`
- `get_stock_realtime_snapshot(symbol)`
- `get_stock_orderbook_snapshot(symbol)`
- `get_stock_minute_replay_snapshot(symbol, end_day, limit_days)`
- `get_recent_market_events(limit, event_type)`
- `get_signal_snapshot(symbol)`
- `get_event_scoring_config()`
- `get_realtime_connection_status()`
- `explain_market_event(event_id)`
- `review_candidate_outcome(symbol, trading_day)`
- `record_candidate_outcome(...)`

The second-board candidate pool is currently derived from jvQuant semantic queries for yesterday limit-up stocks with current strength. Auction metrics, capital-flow net inflow ratio, concept/topic tags, first/final seal time, seal amount, max seal amount, break/reseal counts, seal volume, and seal-to-turnover ratio come from jvQuant semantic fields when available. Aegis Alpha now also calls jvQuant `client.minute(..., mode=minute)` for minute replay and recalculates 1/3/5/10-minute speed windows from minute bars when available. In that case speed fields use `minute_replay_exact_window:...` or `minute_replay_partial_window:...`; if minute replay is unavailable or disabled, the adapter falls back to jvQuant semantic speed fields such as `provider_exact_window:...` or `provider_latest_rolling_5m`. True own-order queue position still requires broker order/trade callbacks, so the current output only exposes a queue-position note from the read-only orderbook summary. Historical limit-up statistics and normalized theme strength still use placeholders until dedicated scanners are implemented.

Minute replay is not tick-by-tick realtime Level-2. During active trading, agents must inspect `minute_replay_timestamp`, `five_min_speed_timestamp`, and the relevant orderbook timestamp before treating a conclusion as fresh enough for intraday monitoring.

Aegis Alpha now also has the first event-driven layer:

- `config/event_scoring.yaml` controls event triggers, scoring weights, freshness limits, and suggested agent actions.
- `SignalSnapshot` is the agent-safe signal surface for one symbol.
- `MarketEvent` is the agent-safe event surface for theme clusters, approaching limit-up, big-order inflow spikes, second-board reprice, and seal-order risk.
- jvQuant WebSocket `lv1/lv2/lv10` has a wrapper for connection/subscription callbacks; raw WebSocket messages are kept inside the market engine and are not exposed through MCP.
- SQLite stores structured events, signal snapshots, reviews, and provider runs under `data/aegis_alpha.db` by default. Parquet storage is reserved for high-volume bars, ticks, and orderbook snapshots after a dedicated writer is added.

Preview jvQuant WebSocket subscription commands without opening a stream:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_jvquant_realtime.py --symbols 600519 --levels lv1,lv2
```

Open a short read-only WebSocket smoke subscription:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_jvquant_realtime.py --symbols 600519 --levels lv1,lv2,lv10 --connect --duration 5
```

Each second-board candidate also includes `data_quality`, a per-signal metadata map covering source, source field, timestamp, confidence, grading usability, limitations, and evidence. Evidence entries use `authority` to separate `official_doc`, `observed_probe`, and `internal_inference`. Current jvQuant official capability notes are documented in [docs/JVQUANT_OFFICIAL_INDEX.md](docs/JVQUANT_OFFICIAL_INDEX.md), and observed semantic-query probes are documented in [docs/JVQUANT_FIELD_MAP.md](docs/JVQUANT_FIELD_MAP.md) and [docs/JVQUANT_CAPABILITY_MATRIX.md](docs/JVQUANT_CAPABILITY_MATRIX.md).

Use `get_second_board_candidates_compact(limit)` for routine agent screening, then `get_second_board_candidate_data_quality(symbol)` when an agent only needs evidence details for one candidate; both avoid pulling the full verbose candidate pool and reduce output truncation.

Refresh the jvQuant field probe after provider changes:

```bash
PYTHONPATH=src .venv/bin/python scripts/probe_jvquant_fields.py --sample-limit 2 --format markdown --output docs/JVQUANT_FIELD_MAP.md
PYTHONPATH=src .venv/bin/python scripts/probe_jvquant_fields.py --sample-limit 1 --format matrix --output docs/JVQUANT_CAPABILITY_MATRIX.md
```

## Install Or Verify Hermes

Aegis Alpha includes a helper that checks for Hermes and can run the official Hermes installer when explicitly requested:

```bash
scripts/install_hermes.sh
scripts/install_hermes.sh --run
```

The helper defaults to dry-run mode. It does not modify Hermes, fork Hermes, or vendor Hermes code. See [docs/HERMES.md](docs/HERMES.md) for the integration details.

To install only Hermes, the project skill, the MCP config, and run the integration check in one flow:

```bash
scripts/install_hermes_all.sh
```

## Install The Hermes Skill

Aegis Alpha includes a project skill for Hermes:

```text
.hermes/skills/second-board-radar/SKILL.md
```

Copy it into Hermes when you want Hermes to reason over the Aegis Alpha MCP tools with the project's second-board rules:

```bash
scripts/install_hermes_skill.sh
```

See [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) for the AI integration model.

## Install Hermes MCP Config

Install the Aegis Alpha MCP config snippet into Hermes:

```bash
scripts/install_hermes_mcp_config.sh
```

Check the local Hermes integration state:

```bash
scripts/check_hermes_integration.sh
```

## Run The MCP Server

```bash
aegis-alpha-mcp
```

Hermes can be configured to launch this command as a local MCP server. The server uses deterministic mock data by default, and can use authorized read-only jvQuant data when `.env.local` selects the jvQuant provider.

## MCP Tools

The MVP exposes these read-only tools:

- `get_market_snapshot`
- `get_market_sentiment_gate`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_realtime_snapshot`
- `get_stock_orderbook_snapshot`
- `get_stock_minute_replay_snapshot`
- `get_recent_market_events`
- `get_signal_snapshot`
- `get_event_scoring_config`
- `get_realtime_connection_status`
- `explain_market_event`
- `review_candidate_outcome`
- `record_candidate_outcome`
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

`explain_second_board_candidate(symbol)` focuses on second-board logic: market sentiment gate, 5-minute speed, big-order net inflow ratio, first limit-up time, seal amount, seal-to-turnover ratio, queue-position note, same-theme co-movement, orderbook quality, and three-year historical limit-up/gap-up placeholders.

## Development Checks

```bash
python -m compileall src scripts tests
PYTHONPATH=src python scripts/smoke_check.py
```

## Security Boundary

Do not commit real secrets, API keys, broker tokens, Level-2 credentials, or account identifiers. Use `.env.example` as a local template and keep real values in `.env.local`.

Real trading tools are intentionally absent from this MVP. Future trading actions must be added behind explicit risk controls, audit logs, and human confirmation.

## Packaging Direction

The MVP ships as a Python package with a console command because this is easiest to inspect and debug while MCP contracts are still evolving. Once stable, the same server can be packaged as a Docker image or standalone binary.
