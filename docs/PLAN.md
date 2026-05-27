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

## Phase 0: Hermes Companion Setup

Provide a thin helper around the official Hermes installer and document how to register Aegis Alpha in `~/.hermes/config.yaml`.

Rules:

- Do not fork Hermes.
- Do not patch Hermes.
- Do not vendor Hermes code.
- Use documented MCP configuration as the integration surface.
- Keep installer execution explicit through `scripts/install_hermes.sh --run`.

## Phase 1: Read-Only MCP

Build a safe second-board watchlist assistant with mock data first, then connect authorized market-data providers.

Initial tools:

- `get_market_snapshot`
- `get_market_sentiment_gate`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_realtime_snapshot`
- `get_stock_orderbook_snapshot`
- `get_stock_history_limitup_stats`
- `get_theme_strength`
- `get_second_board_candidates`
- `explain_candidate`
- `explain_second_board_candidate`

The output must stay structured, timestamped, and explicit about data quality. `explain_candidate` must describe observations, risks, trigger conditions, and avoid conditions instead of issuing buy or sell instructions.

## Phase 2: Morning Second-Board Radar

Add real-time adapters for providers such as jvQuant, StockApi, MyQuant, or miniQMT.

Current jvQuant-backed coverage includes market gate, limit-up pool, break-board pool, single-symbol snapshots, orderbook snapshots, a coarse second-board candidate pool, semantic-query five-minute speed with parsed provider windows when available, semantic-query capital-flow net inflow ratio, first limit-up time, seal amount, seal volume, and seal-to-turnover ratio. Exact minute-bar or tick recalculation is still pending. True own-order queue position still requires broker order/trade callbacks, so Aegis Alpha currently exposes a read-only queue-position note instead of a real order position. The next gaps are tick-level big-order classification and historical follow-through statistics.

The candidate contract now includes `data_quality` metadata per core signal. Keep expanding this layer before making strategy decisions stricter: every signal should declare its provider source, raw field name, timestamp, confidence, grading usability, limitations, and evidence. Evidence authority must distinguish official docs, observed API probes, and internal inference.

Capability discovery now has two tracks:

- Official documentation index: [JVQUANT_OFFICIAL_INDEX.md](JVQUANT_OFFICIAL_INDEX.md)
- Observed semantic-query capability matrix: [JVQUANT_CAPABILITY_MATRIX.md](JVQUANT_CAPABILITY_MATRIX.md)

Core indicators:

- Market sentiment gate.
- Yesterday limit-up pool.
- Second-board candidate pool.
- First limit-up time, seal amount, seal volume, and seal-to-turnover ratio.
- Queue-position note from orderbook summary; real queue position only after broker order tracking exists.
- Limit-up pool and break-board pool.
- Break-board rate.
- 5-minute speed.
- Big-order net inflow.
- Order-book quality.
- Theme strength.
- Same-theme rising count and leader status.
- Historical limit-up success rate.
- Historical next-day premium.
- Historical third-day premium after sealed second board.

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

Second-board reviews should record:

- Whether the candidate reached the limit-up price.
- Whether the second board sealed.
- Whether it broke board after sealing.
- Next-day open and intraday high.
- Third-day premium after a sealed second board.

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
