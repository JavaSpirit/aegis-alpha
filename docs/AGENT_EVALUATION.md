# Agent Evaluation

Aegis Alpha evaluates agent behavior separately from market data ingestion. The goal is to verify that Hermes/DeepSeek can explain structured `MarketEvent` data without turning read-only research into direct trading instructions.

## Offline Replay Smoke Test

Run the synthetic second-board replay through DeepSeek:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_agent_replay.py
```

Optional stale-data test:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_agent_replay.py --stale
```

Run one historical SQLite snapshot through DeepSeek:

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_agent_historical_snapshot.py --target-time 2026-05-29T10:00:00+08:00 --symbols 600519,000001
```

Run a batch of historical SQLite snapshots:

```bash
PYTHONPATH=src .venv/bin/python scripts/batch_agent_historical_eval.py --symbols 600519,000001
```

Batch reports are written under `data/agent_eval_runs/` and are ignored by git.

The script reads `DEEPSEEK_API_KEY` from `.env.local` or the shell environment and does not print the key.

## Expected Behavior

- Output must be valid JSON.
- `natural_language_reason` must explain the rating in Chinese.
- The agent must state that the replay is offline or synthetic.
- The agent must include a non-investment-advice disclaimer.
- The agent must not give direct buy, sell, or order instructions.
- If data is stale, the rating must be capped at `B`, `C`, or `REJECT`.
- Internally estimated orderbook metrics must not be described as exchange-authoritative Level-2 queue position.

## Field Units

Agent prompts and MCP consumers must use the shared context from `aegis_alpha.agent_context`.

- Fields ending with `_pct` are already percent values. `0.0929` means `0.0929%`, not `9.29%`.
- Fields ending with `_ratio` are ratios. `0.0311` means `3.11%`.
- Fields ending with `_score` are 0-100 internal scores unless documented otherwise.
- Fields ending with `_cny` are CNY amounts.
- Realtime orderbook metrics are internal estimates from `lv10` depth unless official provider evidence says otherwise.

## Source Boundary

The replay fixture validates this path:

```text
synthetic lv10-like depth
  -> orderbook metrics
  -> SignalSnapshot
  -> MarketEvent
  -> DeepSeek explanation
  -> policy checks
```

It is not live market data and must not be used as a trading signal.
