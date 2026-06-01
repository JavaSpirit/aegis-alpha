# Future Roadmap: jvQuant Real Integration

> **Status: ROADMAP — not scheduled.** This is a forward-looking design doc, not a task plan. It does not commit any agent or sub-agent to implement. Treat as the "ready when needed" spec for the day we actually run probes against live jvQuant and decide which placeholders can be wired.

> **Why this is a roadmap, not a P8 plan:** P5/P6 left 7 jvQuant `data_mode=placeholder` paths because the implementer didn't have ground-truth field returns. Writing a code-only plan against guessed Chinese semantic queries would risk repeating that mistake. This document codifies the probe-first workflow so any future P-phase that picks this up has zero ambiguity about how to start.

---

## 1. The Seven Placeholders (Inventory)

| # | Method | File:Line | Officially documented? | Likely path |
|---|--------|-----------|------------------------|-------------|
| 1 | `JvQuantMarketDataAdapter.get_dragon_tiger` | `adapters/jvquant/adapter.py:804` | ❌ Not in `JVQUANT_OFFICIAL_INDEX.md` | External source likely required |
| 2 | `JvQuantMarketDataAdapter.get_active_seats_today` | `adapters/jvquant/adapter.py:821` | ❌ Same as above | External source likely required |
| 3 | `JvQuantMarketDataAdapter.get_limit_down_pool` | `adapters/jvquant/adapter.py:838` | ⚠️ Possibly via semantic query (`今日跌停,...`) | Probe required |
| 4 | `JvQuantMarketDataAdapter.get_st_pool` | `adapters/jvquant/adapter.py:842` | ⚠️ Possibly via semantic query (`是否ST=是,...`) | Probe required |
| 5 | `JvQuantMarketDataAdapter.get_capital_flow_slices` | `adapters/jvquant/adapter.py:846` | ⚠️ Minute replay returns bars but no documented "big_order / main / retail" decomposition per-minute | Probe required; may need k-line + tick fusion |
| 6 | `JvQuantMarketDataAdapter.get_weekly_position` | `adapters/jvquant/adapter.py:853` | ✅ K-line endpoint documented (`mode=kline`) | Compute on top of k-line; no probe needed |
| 7 | `JvQuantMarketDataAdapter.get_new_stock_candidates` | `adapters/jvquant/adapter.py:880` | ⚠️ Possibly via semantic query on listing date | Probe required |
| 8 | `JvQuantMarketDataAdapter.get_suspended_stocks` | `adapters/jvquant/adapter.py:884` | ⚠️ Possibly via semantic query (`今日停牌,...`) | Probe required |

**Note:** Item 8 numbered 8th but there are only 7 placeholder methods + 1 placeholder-with-signal (`get_active_seats_today`). The phrase "7 placeholders" in earlier discussion is approximate — count by file is 8 method bodies, of which `get_active_seats_today` already returns a `data_mode=placeholder` signal.

## 2. Three Tiers by Confidence

### Tier 1 — High confidence (probe likely succeeds)

Items where jvQuant has documented capability OR the semantic-query pattern is well-established:

- **Weekly position (`get_weekly_position`)** — K-line endpoint is officially documented (`mode=kline`). Compute weekly OHLC + position-pct + ma20/ma60 from k-line data ourselves. **No probe needed; pure derivation.**
- **Limit-down pool (`get_limit_down_pool`)** — Mirror of `今日涨停` query that's already proven for second-board candidates. Probe `今日跌停,股票代码,股票简称,涨跌幅,...` and confirm the columns.
- **ST pool (`get_st_pool`)** — Existing semantic queries already include `是否ST` field (visible in `docs/JVQUANT_FIELD_MAP.md`). Probe `是否ST=是,股票代码,...` and confirm.

### Tier 2 — Medium confidence (probe must succeed before commit)

Items where the semantic query SHOULD work but field names need verification:

- **New stocks (`get_new_stock_candidates`)** — jvQuant likely has `上市日期` or `上市天数` field. Probe `上市天数小于180,股票代码,股票简称,流通市值,...`. If `上市日期` returns ISO date strings, derive `days_since_listing` ourselves.
- **Suspended stocks (`get_suspended_stocks`)** — Probe `今日停牌,股票代码,股票简称,停牌原因,停牌起始日,复牌日,...`. Field name guesses are common Chinese terms but unverified.
- **Capital flow slices (`get_capital_flow_slices`)** — jvQuant minute replay returns time/last_price/volume/average_price. Splitting into "big_order / main / retail" likely requires the **逐笔委托队列** endpoint (`mode=order_queue`), which is documented but pricier. Otherwise we proxy via volume * (last_price - prev_price) bucketing.

### Tier 3 — Low confidence (may stay placeholder forever)

Items where jvQuant likely doesn't expose the data at all:

- **Dragon Tiger (`get_dragon_tiger` / `get_active_seats_today`)** — Not in jvQuant's documented capability list. Real source is probably 通达信 / 同花顺 / 东财 龙虎榜 web-scraped or a separate vendor. Aegis Alpha's options:
  - **Option A (preferred):** Add a separate `aegis_alpha/adapters/dragon_tiger_external/` adapter with its own data source (Tushare, Akshare, or scraped JSON), keeping `JvQuantMarketDataAdapter` returning placeholder.
  - **Option B:** Accept that this stays placeholder until a 龙虎榜 source is contracted. Mock data + skill warnings about `data_mode=placeholder` already cover the agent UX.

## 3. The Probe-First Workflow (Mandatory)

Before any jvQuant placeholder method is wired, a probe must demonstrate the actual returned columns. This is non-negotiable — it's the lesson learned from P5/P6.

### Prerequisites

```bash
# 1. Install jvQuant SDK
.venv/bin/pip install ".[jvquant]"

# 2. Provide token in .env.local (NEVER commit)
cat >> .env.local <<EOF
AEGIS_ALPHA_MARKET_DATA_PROVIDER=jvquant
JVQUANT_TOKEN=<your-token>
JVQUANT_MARKET=ab
EOF

# 3. Verify SDK + token together
.venv/bin/python scripts/smoke_jvquant_readonly.py --symbol 600519
# Expect: minute replay snapshot + 5-min speed payload (no secrets printed)
```

### Probe loop (per subsystem)

For each Tier 1/2 placeholder:

#### A. Add probe to `config/jvquant_capability_probes.json`

Append a new probe block. Example for limit-down pool:

```json
{
  "name": "limit_down_pool",
  "capability": "limit_down_pool",
  "query": "今日跌停,股票代码,股票简称,涨跌幅,连续跌停天数,价格,成交额,行业",
  "sort_key": "涨跌幅"
}
```

#### B. Run the probe

```bash
PYTHONPATH=src .venv/bin/python scripts/probe_jvquant_fields.py \
    --sample-limit 3 --format markdown --output docs/JVQUANT_FIELD_MAP.md
```

#### C. Inspect the output

Open the updated `docs/JVQUANT_FIELD_MAP.md`. The probe writes the actual `Returned fields` and 1-3 `Sample row` payloads. Three possible outcomes:

| Outcome | Action |
|---------|--------|
| Returns sensible data with expected columns | **Proceed to wire.** Note any column rename (e.g. `连续跌停天数` may actually return as `连跌天数`). |
| Returns empty `[]` | **Re-probe** with different query terms (e.g. drop conditions one at a time). If all variants empty, jvQuant likely doesn't expose this data. Fall to Tier 3 treatment. |
| Returns error / 401 / rate-limit | Token issue or query syntax invalid. Fix the query, NOT the field map. |

#### D. Append fields to capability matrix

`docs/JVQUANT_CAPABILITY_MATRIX.md` documents which capabilities are confirmed. Add a row:

```markdown
| limit_down_pool | observed_probe | 2026-mm-dd | confirmed: 股票代码, 股票简称, 涨跌幅, ... |
```

#### E. Then and only then write the parser + wire the adapter

The parser code goes in a new module under `extensions/` (matching P5/P6 layout). Adapter method body becomes a real `_query` call + parser invocation. Tests use the actual probe sample as fixture (not invented data).

## 4. Per-Subsystem Roadmap

Each subsystem below is a self-contained "future P-phase task batch" — typically 2-4 tasks. Do NOT pre-write Chinese semantic queries or parsers without a probe first.

### Subsystem A — Weekly Position (Tier 1, no probe)

**Why first:** No probe needed (k-line is officially documented). Self-contained derivation. Touches only `weekly_position.py` + adapter method.

**Sketch:**

1. Extend `JvQuantMarketDataAdapter` to call `client.kline(code=symbol, mode='week', limit=12)` (verify exact API signature against jvquant SDK's `dir(client)`).
2. Take last 8 weekly bars.
3. Compute:
   - `weekly_high` = max(high) over last 8 weeks
   - `weekly_low` = min(low) over last 8 weeks
   - `weekly_close` = last week's close
   - `position_pct` = (close - low) / (high - low)
   - `weeks_in_uptrend` = consecutive weeks where `close > prev_close` ending at today
   - `ma20_above_ma60` = (sum(close[-20:])/20) > (sum(close[-60:])/60) — but weekly bars only give 8-12, so re-fetch 60 weeks of daily bars or accept "not enough data" → `ma20_above_ma60 = False`.
4. Replace placeholder body in `get_weekly_position`.
5. Test against fixture from minute_replay-style mock client.

**Risk:** jvQuant k-line API signature unknown; the `client.kline` call is a guess. Verify SDK first.

### Subsystem B — Limit-Down Pool (Tier 1)

**Probe step:** Add `limit_down_pool` query to probe config. Run probe. Capture returned fields.

**If probe succeeds:**
- Write `extensions/limit_down_parser.py` with `parse_limit_down_payload(payload, *, trading_day) -> list[ContrarianPoolEntry]`
- Replace `get_limit_down_pool` body with `_query(...) → parse(...)`
- Tests use captured probe sample as fixture

**If probe returns empty:** keep placeholder, document why in `docs/JVQUANT_CAPABILITY_MATRIX.md`.

### Subsystem C — ST Pool (Tier 1)

Same shape as Subsystem B, but with `是否ST=是` filter. Likely the lightest task because `是否ST2026-MM-DD` field is already in existing field map.

### Subsystem D — Suspended Stocks (Tier 2)

**Probe step:** Try multiple query variations because suspended-stock semantic-query terms are unstandardized:

- `今日停牌,股票代码,股票简称,停牌原因,停牌起始日,复牌日,行业`
- `停牌中,股票代码,...`
- `停牌状态=停牌,股票代码,...`

**If a variant returns rows:** wire it. Be aware that jvQuant probably gives only "currently suspended", not historical suspensions. The `suspension_start_day` and `suspension_end_day` fields may need fallback to "today / blank" if jvQuant doesn't expose them.

**If all empty:** keep placeholder. Suspended stock data has external sources (Akshare, Tushare).

### Subsystem E — New Stock Candidates (Tier 2)

**Probe variations:**

- `上市天数小于180,股票代码,股票简称,流通市值,涨跌幅,行业`
- `上市日期大于2025-01-01,股票代码,...` (date filtering)
- `次新股,股票代码,...` (does jvQuant have a "次新" semantic shortcut?)

If `上市日期` returns ISO date string, compute `days_since_listing` Python-side via `(today - parse(listing_date)).days`. If jvQuant gives `上市天数` directly, use it.

If `流通市值` is in 元 (yuan), no transform; if in 万元, multiply by 10000.

### Subsystem F — Capital Flow Slices (Tier 2 — risky)

**Why risky:** P5/P6 designed `pre_first_seal_5m / post_break_1m / tail_30m` windows assuming we'd have per-minute big-order net inflow. jvQuant's documented endpoints:

- Minute replay: time/last_price/volume/average_price (no big-order classification)
- Order queue (`mode=order_queue`): tick-level orders (premium endpoint)
- Capital flow at **day level**: visible in `资金流向` field of existing semantic queries

**Realistic path:** drop the per-minute granularity goal. Instead:

- Make `get_capital_flow_slices` return day-level net inflow for the symbol (one row, not 3 windows).
- Repurpose the `CapitalFlowSliceWindow` Literal to add `"daily"` and treat the existing 3 windows as Tier 3 (mock-only) until tick data justifies the cost.

This is a **scope reduction**, not full wiring. Document the reduction clearly in the SKILL workflow.

### Subsystem G — Dragon Tiger (Tier 3 — external source)

**Decision needed before any code:** does the user want to:

- (a) Add a new external adapter (`adapters/dragon_tiger_external/`) using Akshare or scraped data — significant new dependency, ongoing scrape maintenance.
- (b) Wait for a paid 龙虎榜 vendor and write the adapter against that.
- (c) Accept placeholder forever; mock data + skill `data_mode=placeholder` warning is enough.

If (a) or (b): the work is shaped like a new mini-subsystem, not a "wire jvquant" task. Treat as a separate plan when triggered.

If (c): no work. Skill already tells the agent placeholder = don't trust.

## 5. Pre-Flight Checklist

Before any code task in this roadmap runs, the following must be true:

- [ ] `.venv/bin/pip show jvquant` returns version info (SDK installed)
- [ ] `JVQUANT_TOKEN` is set in `.env.local` (never committed)
- [ ] `scripts/smoke_jvquant_readonly.py --symbol 600519` runs cleanly (token + SDK working together)
- [ ] User has read this roadmap and explicitly green-lit the subsystem(s) to implement
- [ ] At least 30 minutes of free token quota for the day (probe scripts spend quota)

## 6. Anti-Patterns to Avoid

If a future agent picks up this roadmap, these are the failure modes from P5/P6 that this document is trying to prevent:

1. **Don't write Chinese semantic queries from imagination.** Every query must come from a probe that returned actual data, captured in `docs/JVQUANT_FIELD_MAP.md`.

2. **Don't hardcode field names.** Use `_first_field_value(row, "涨跌幅", "涨幅")` style fallbacks (existing pattern in `parsers.py`) so column renames don't silently break parsers.

3. **Don't claim `data_mode="real"` without an actual probe-confirmed query.** If the query was probe-confirmed but returned empty for a particular call, return empty list with `data_mode="real"`. If the endpoint itself wasn't confirmed, keep `data_mode="placeholder"`.

4. **Don't wire all 7 placeholders in one big-bang plan.** Each subsystem is a 2-4 task batch with its own probe + wire + test. Land one subsystem per phase if needed.

5. **Don't skip the probe sample as test fixture.** When you wire a parser, save 1-3 actual probe rows as a test fixture file (e.g. `tests/fixtures/jvquant_limit_down_2026-06-01.json`). This lets the test verify against real shape, not invented shape.

6. **Don't claim work is done if probe stayed empty.** Empty probe → placeholder stays. Document in `docs/JVQUANT_CAPABILITY_MATRIX.md` that the capability was probed and not found.

## 7. Trigger Conditions (When to Pick This Up)

Reasons to start executing this roadmap:

- User has time + token to run probes interactively
- Hermes use case where "channel = placeholder" is hurting the agent's ability to give a useful answer (e.g., user asks "is 章盟主 active today?" and the placeholder data forces a non-answer)
- jvQuant releases a documented dragon-tiger or capital-flow endpoint
- A separate vendor (Akshare / Tushare / paid feed) is contracted

Reasons NOT to start:

- "Cleanup phase" — placeholders aren't bugs; they're honest signals. Removing them isn't worth the risk if no real data source is ready.
- Pure architectural urge — refactoring placeholder method bodies without new capability is busywork.
- Without a token — pure code-only work will repeat P5/P6's mistake.

## 8. Estimated Effort (Rough)

Assuming all prerequisites met:

| Subsystem | Probe | Parser + wire | Tests | Total |
|-----------|-------|---------------|-------|-------|
| A. Weekly position | 0 | 4-6 hours | 1 hour | ~1 day |
| B. Limit-down pool | 1 hour | 2 hours | 30 min | ~half day |
| C. ST pool | 30 min | 1 hour | 30 min | ~quarter day |
| D. Suspended stocks | 2 hours (multiple variants) | 2 hours | 30 min | ~half day |
| E. New stock candidates | 2 hours (multiple variants) | 3 hours | 1 hour | ~3/4 day |
| F. Capital flow slices | 2 hours probe + scope decision | 2-4 hours | 1 hour | ~1 day |
| G. Dragon Tiger | external source decision | 1-3 days | 1 day | **separate plan** |

Subsystems A-E + maybe F: total ~3-4 days of focused work, gated on probe successes.

Subsystem G is a separate roadmap and should be its own plan when triggered.

## 9. What Belongs in This Document vs What Belongs in P8

This document: **what to do, why, in what order, when.**

A future P-phase plan that picks one or more subsystems above: **TDD task-by-task code spec** with concrete test fixtures from probe samples.

The two should not collapse. Roadmap-as-plan was the P5/P6 mistake we're correcting.

---

## Maintenance

Update this document when:

- A subsystem is implemented (mark Tier 1/2/3 result)
- A probe reveals jvQuant's real field names → update Subsystem section
- A new placeholder is added (rare in steady state)
- A new external data source is contracted (e.g., for Dragon Tiger)

Last updated: 2026-06-01 — initial roadmap, no implementation yet.
