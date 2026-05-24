# Aegis Alpha Plan

## Summary

Aegis Alpha starts as a read-only MCP server for Hermes. Its first job is to help observe A-share markets, especially morning limit-up and break-board behavior, without touching real accounts or credentials.

The long-term direction is a layered trading assistant:

```text
Hermes memory and skills
  -> Aegis Alpha MCP tools
  -> Market-data adapters
  -> Signal and risk engines
  -> Paper trading
  -> Controlled real trading
```

## Phase 1: Read-Only MCP

Build a safe watchlist assistant with mock data first, then connect authorized market-data providers.

Initial tools:

- `get_market_snapshot`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_realtime_snapshot`
- `get_stock_history_limitup_stats`
- `get_theme_strength`
- `explain_candidate`

The output must stay structured, timestamped, and explicit about data quality. `explain_candidate` must describe observations, risks, trigger conditions, and avoid conditions instead of issuing buy or sell instructions.

## Phase 2: Morning Limit-Up Radar

Add real-time adapters for providers such as jvQuant, StockApi, MyQuant, or miniQMT.

Core indicators:

- Limit-up pool and break-board pool.
- Break-board rate.
- Seal amount and seal amount ratio.
- Reopen count.
- Big-order net inflow.
- Order-book quality.
- Theme strength.
- Same-theme leader status.
- Historical limit-up success rate.
- Historical next-day premium.

The first production-grade scoring output should use grades such as `A`, `B`, `C`, and `REJECT`.

## Phase 3: Review And Correction

Add daily review records so Hermes can learn user preferences through skills.

Examples:

- Which candidates were promoted.
- Which candidates were rejected.
- Whether a board stayed sealed.
- Next-day premium.
- User corrections.
- Rule changes extracted into Hermes skills.

This phase turns Aegis Alpha from a static screener into a feedback-driven assistant.

## Phase 4: Medium And Long-Term Module

Add a separate research path for medium and long-term analysis. It should not reuse short-term limit-up scoring.

Candidate tools:

- Fundamentals.
- Valuation history.
- Industry comparison.
- Financial statements.
- News and event risk.
- Factor screening through Qlib, Hikyuu, or custom research code.

## Phase 5: Paper Trading

Add paper-trading tools before any real order integration.

Candidate tools:

- `create_paper_order`
- `close_paper_position`
- `get_paper_portfolio`
- `review_paper_trade`

Paper trading validates signal quality, user preference learning, risk rules, and operational workflow.

## Phase 6: Controlled Real Trading

Real trading is out of scope for the MVP. If added later, it must be a narrow, auditable, two-step flow:

```text
Hermes proposes
  -> risk engine validates
  -> user confirms
  -> trading adapter executes
```

Required controls:

- Real trading disabled by default.
- Single-position limits.
- Daily loss limits.
- Daily order count limits.
- Symbol blacklist.
- Duplicate-order prevention.
- Price deviation checks.
- Global kill switch.
- Human confirmation.

