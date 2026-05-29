# Aegis Alpha Plan

## Summary

Aegis Alpha starts as a Hermes companion plus read-only MCP server. Its first product focus is a second-board radar: decide whether the market is suitable for board-chasing, then monitor yesterday limit-up stocks that may advance to a second board.

The long-term direction is a layered trading assistant:

```text
Hermes memory and skills
  -> Aegis Alpha MCP tools
  -> Market-data adapters
  -> Second-board signal and risk engines
  -> Paper trading
  -> Controlled real trading
```

This document captures **product intent and phase boundaries**. The engineering implementation roadmap (with tasks, file paths, and acceptance criteria) lives in [superpowers/plans/2026-05-29-aegis-alpha-roadmap.md](superpowers/plans/2026-05-29-aegis-alpha-roadmap.md).

## Phase 0 — Hermes Companion Setup

Goal: register Aegis Alpha as a Hermes MCP server without forking or patching Hermes.

Rules:

- Do not fork, patch, or vendor Hermes.
- Use documented MCP configuration as the integration surface.
- Keep installer execution explicit; never auto-run third-party installers without user opt-in.

## Phase 1 — Read-Only MCP

Goal: a safe second-board watchlist assistant with mock data first, then authorized read-only providers.

Acceptance: every MCP response is structured, timestamped, and explicit about data quality. Tools that explain candidates describe observations / risks / trigger conditions / avoid conditions, never buy/sell instructions.

## Phase 2 — Morning Second-Board Radar

Goal: connect a real provider (jvQuant currently) and produce A/B/C/REJECT grades for second-board candidates with `data_quality` evidence per signal.

Open gaps: tick-level big-order classification, normalized theme strength, three-year historical follow-through statistics, true own-order queue position.

## Phase 2.5 — Realtime Events And Local Data Layer

Goal: let WebSocket data drive a local market engine, not the agent. Agents only see structured `SignalSnapshot` and `MarketEvent` outputs.

Boundaries:

- Raw WebSocket messages stay inside the local engine.
- Events carry evidence, freshness status, score, confidence, and suggested agent actions (analysis prompts, not orders).
- Persistence layer is SQLite for events / snapshots / reviews / corrections / proposals; Parquet is reserved for high-volume historical bars and tick data.

## Phase 2.6 — Launchd-Managed Runner

Goal: separate process lifecycle from market-session lifecycle.

- launchd keeps the runner process alive.
- Aegis Alpha decides when (and whether) to open WebSocket subscriptions based on configured trading sessions.
- MCP and Hermes only read the runner's local state; they never own the realtime process.

## Phase 3 — Review And Correction

Goal: turn Aegis Alpha from a static screener into a feedback-driven assistant. User corrections feed back through structured proposals; Aegis Alpha records evidence and routes follow-up but does not auto-mutate Hermes memory, skills, or scoring config.

Acceptance: a candidate review captures whether it touched limit-up, sealed second board, broke board after sealing, next-day open and intraday high, and third-day premium.

## Phase 4 — Medium And Long-Term Module

Goal: a separate research path for medium and long-term analysis. Must not reuse short-term limit-up scoring. Candidate inputs include fundamentals, valuation history, industry comparison, news/event risk, and factor screening.

## Phase 5 — Paper Trading

Goal: validate signal quality, user preference learning, risk rules, and operational workflow before any real-money path. Paper trading tools are added behind the same MCP boundary, with explicit `paper_*` naming.

## Phase 6 — Controlled Real Trading

Out of scope for the MVP. If added later, it must be a narrow, auditable, two-step flow:

```text
Hermes proposes -> risk engine validates -> user confirms -> trading adapter executes
```

Required controls before any real-money path: real trading disabled by default; single-position and daily-loss limits; daily order-count limits; symbol blacklist; duplicate-order prevention; price deviation checks; global kill switch; human confirmation.
