# Future Roadmap: jvQuant Real Integration

> **Status: LIVE-PROBE UPDATED ROADMAP — confirmed wiring completed.** This document includes live jvQuant observations from 2026-06-01 23:39 Asia/Shanghai. The capabilities marked "wired" were implemented in P8; active-seat alias aggregation and minute-level semantic capital-flow slices remain deliberately out of scope.

> **Why this is a roadmap, not a P8 plan:** P5/P6 left 7 jvQuant `data_mode=placeholder` paths because the implementer didn't have ground-truth field returns. Writing a code-only plan against guessed Chinese semantic queries would risk repeating that mistake. This document codifies the probe-first workflow so any future P-phase that picks this up has zero ambiguity about how to start.

---

## 0. Live Probe Findings (2026-06-01)

Environment:

- SDK installed: `jvquant==1.20.5`
- Token present in `.env.local`; no secrets printed
- Smoke command passed: `.venv/bin/python scripts/smoke_jvquant_readonly.py --symbol 600519 --timeout 30`
- `level_queue(600519)` returned an account quota error: current account has fewer than 60000 points, so queue/depth endpoints are test-limited
- `order_book(600519, 0)` returned fields `offset`, `price`, `volume`, `type`, `time` with 192 rows

Observed semantic-query capabilities:

| Capability | Probe query | Status | Observed fields / shape | Decision |
|---|---|---:|---|---|
| Weekly K-line | `client.kline("600519", "stock", "前复权", "week", 12)` | available | `日期`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率` | Wired in P8 |
| Limit-down pool | `今日跌停,股票代码,股票简称,涨跌幅,连续跌停天数,价格,成交额,行业` | available, count 23 | `代码`, `名称`, `涨跌幅2026-06-01`, `是否跌停2026-06-01`, `连续跌停天数(天)2026-06-01`, `收盘价(日线不复权)2026-06-01`, `成交额2026-06-01` | Wired in P8 |
| ST pool | `是否ST=是,股票代码,股票简称,涨跌幅,价格,成交额,行业` | available, count 248 | `代码`, `名称`, `是否ST2026-06-01`, price/amount fields; some rows have `-` for halted/no-trade values | Wired in P8 |
| New stocks | `上市天数小于180,...` / `次新股,...` | available, counts 78 / 135 | `上市日期`, `上市天数(天)2026-06-01`, `流通市值(日线不复权)2026-06-01` | Wired in P8 |
| Suspended stocks | `今日停牌,...`; `停牌中,...`; `停牌状态=停牌,...` | fields observed, count 0 | `停牌起始日期2026-06-01`, `停牌原因2026-06-01`, `停牌@截至2026-06-01最新`, `复牌@截至2026-06-01最新` | Wired in P8 as confirmed-empty capable |
| Dragon Tiger | `今日龙虎榜,股票代码,股票简称,上榜原因,买入金额,卖出金额,净买入额` | available, count 97 | Top-level fields `代码`, `名称`, `龙虎榜2026-06-01`; value is a nested list of榜单 dictionaries containing `上榜原因`, `买入额(元)`, `卖出额(元)`, `净买额(元)` | Wired in P8 raw parser |
| Active seats | `今日龙虎榜,营业部名称,...` | partial | Returned the same nested `龙虎榜2026-06-01` shape; sample did not expose stable individual营业部 names | Keep separate; requires more probing or alias logic |
| Daily capital flow | `600519,股票代码,股票简称,主力净额,超大单净额,大单净额,中单净额,小单净额,涨跌幅,成交额` | available, count 1 | `主力净额`, `超大单净额`, `大单净额`, `中单净额`, `小单净额` day-level fields | Wired in P8 daily scope |
| Minute capital-flow slices | minute replay + `order_book` | partial | minute replay has price/volume only; `order_book` has order/trade-like rows but no semantic main/retail decomposition | Scope-reduce; do not claim real minute-level 主力切片 |

## 1. The Seven Placeholders (Inventory)

| # | Method | File:Line | Officially documented? | Likely path |
|---|--------|-----------|------------------------|-------------|
| 1 | `JvQuantMarketDataAdapter.get_dragon_tiger` | `adapters/jvquant/adapter.py:804` | ✅ Observed via semantic query | Implemented: nested `龙虎榜YYYY-MM-DD` parser |
| 2 | `JvQuantMarketDataAdapter.get_active_seats_today` | `adapters/jvquant/adapter.py:821` | ⚠️ Raw 龙虎榜 observed, individual营业部 fields not stable in sample | Keep placeholder until seat-name probe/alias map lands |
| 3 | `JvQuantMarketDataAdapter.get_limit_down_pool` | `adapters/jvquant/adapter.py:838` | ✅ Observed via semantic query | Implemented |
| 4 | `JvQuantMarketDataAdapter.get_st_pool` | `adapters/jvquant/adapter.py:842` | ✅ Observed via semantic query | Implemented with nullable price/amount notes |
| 5 | `JvQuantMarketDataAdapter.get_capital_flow_slices` | `adapters/jvquant/adapter.py:846` | ⚠️ Day-level capital flow observed; minute semantic slices not observed | Implemented as one `"daily"` slice |
| 6 | `JvQuantMarketDataAdapter.get_weekly_position` | `adapters/jvquant/adapter.py:853` | ✅ K-line endpoint observed (`type="week"`) | Implemented on top of week/day K-line |
| 7 | `JvQuantMarketDataAdapter.get_new_stock_candidates` | `adapters/jvquant/adapter.py:880` | ✅ Observed via semantic query | Implemented |
| 8 | `JvQuantMarketDataAdapter.get_suspended_stocks` | `adapters/jvquant/adapter.py:884` | ⚠️ Fields observed, count 0 on 2026-06-01 | Implemented; empty result is confirmed-empty capable |

**Note:** Item 8 numbered 8th but there are only 7 placeholder methods + 1 placeholder-with-signal (`get_active_seats_today`). The phrase "7 placeholders" in earlier discussion is approximate — count by file is 8 method bodies, of which `get_active_seats_today` already returns a `data_mode=placeholder` signal.

## 2. Three Tiers by Confidence

### Tier 1 — Confirmed and wired

Items where live probes returned usable fields and P8 wired the adapter:

- **Weekly position (`get_weekly_position`)** — `kline(..., type="week")` returned 12 weekly bars for `600519`.
- **Limit-down pool (`get_limit_down_pool`)** — `今日跌停,...` returned 23 rows with `是否跌停` and `连续跌停天数`.
- **ST pool (`get_st_pool`)** — `是否ST=是,...` and `ST股,...` both returned 248 rows.
- **New stocks (`get_new_stock_candidates`)** — `上市天数小于180,...` returned 78 rows; `次新股,...` returned 135 rows.
- **Dragon Tiger raw record (`get_dragon_tiger`)** — `今日龙虎榜,...` returned 97 rows with nested榜单 details.
- **Daily capital flow** — day-level `主力/超大单/大单/中单/小单净额` fields returned for a specific symbol and for a pool query.

### Tier 2 — Confirmed shape, careful semantics

Items where fields exist but implementation needs explicit limits:

- **Suspended stocks (`get_suspended_stocks`)** — Three query variants returned confirmed fields but `count=0` on 2026-06-01. P8 wired the parser and treats empty results as confirmed-empty real data.
- **Active seats (`get_active_seats_today`)** — Raw龙虎榜 exists, but the observed sample did not expose stable individual营业部 names, so hot-money alias aggregation cannot be called real yet.
- **Capital flow slices (`get_capital_flow_slices`)** — P8 wired one `"daily"` slice from day-level semantic capital-flow fields. Minute windows remain derived/partial unless built from `order_book`, and even then they are order/trade-direction slices, not vendor-certified主力/散户 slices.

### Tier 3 — Scope-reduced or blocked

Items where jvQuant/account constraints prevent the original contract:

- **Level queue / depth-dependent claims** — Current account received a quota/points error for `level_queue`. Do not design core functionality that requires reliable thousand-level queue access unless account entitlement changes.
- **Minute-level主力资金切片** — No observed endpoint returns minute-level `主力/散户/大单` decomposition. This remains a derived signal only, not `data_mode=real` in the original semantic sense.

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

### Subsystem A — Weekly Position (Tier 1, observed)

**Why first:** K-line is officially documented and live-observed. Self-contained derivation. Touches only `weekly_position.py` + adapter method.

**Sketch:**

1. Extend `JvQuantMarketDataAdapter` to call `client.kline(symbol, "stock", "前复权", "week", 12)`.
2. Take last 8 weekly bars.
3. Compute:
   - `weekly_high` = max(high) over last 8 weeks
   - `weekly_low` = min(low) over last 8 weeks
   - `weekly_close` = last week's close
   - `position_pct` = (close - low) / (high - low)
   - `weeks_in_uptrend` = consecutive weeks where `close > prev_close` ending at today
   - `ma20_above_ma60` = fetch 60 daily bars with `client.kline(symbol, "stock", "前复权", "day", 60)` and compute from daily closes.
4. Replace placeholder body in `get_weekly_position`.
5. Test against a fixture matching observed K-line fields: `日期`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率`.

**Risk:** Weekly rows are newest-first in the observed sample; parser must sort by date before calculating consecutive trend.

### Subsystem B — Limit-Down Pool (Tier 1)

**Probe result:** `今日跌停,股票代码,股票简称,涨跌幅,连续跌停天数,价格,成交额,行业` returned 23 rows on 2026-06-01.

- Write `extensions/limit_down_parser.py` with `parse_limit_down_payload(payload, *, trading_day) -> list[ContrarianPoolEntry]`
- Replace `get_limit_down_pool` body with `_query(...) → parse(...)`
- Tests use observed fields including `是否跌停YYYY-MM-DD` and `连续跌停天数(天)YYYY-MM-DD`

### Subsystem C — ST Pool (Tier 1)

**Probe result:** `是否ST=是,股票代码,股票简称,涨跌幅,价格,成交额,行业` returned 248 rows on 2026-06-01.

- Wire `_query(...) → parse_st_pool_payload(...)`.
- Treat `-` price/amount values as missing, not zero.
- Tests include one normal ST row and one no-price row from the observed shape.

### Subsystem D — Suspended Stocks (Tier 2)

**Probe result:** All three query variations returned confirmed fields but no rows on 2026-06-01:

- `今日停牌,股票代码,股票简称,停牌原因,停牌起始日,复牌日,行业`
- `停牌中,股票代码,...`
- `停牌状态=停牌,股票代码,...`

**Decision:** Wire the parser and adapter as a real confirmed-empty capability. If count is zero, return `[]` with real-data semantics. Use a synthetic row in unit tests to exercise field parsing, plus an observed empty fixture to guard `[]`.

### Subsystem E — New Stock Candidates (Tier 2)

**Probe result:** All planned query variants worked:

- `上市天数小于180,股票代码,股票简称,上市日期,上市天数,流通市值,涨跌幅,行业` returned 78 rows.
- `次新股,股票代码,股票简称,上市日期,上市天数,流通市值,涨跌幅,行业` returned 135 rows.
- `上市日期大于2025-12-01,股票代码,股票简称,上市日期,流通市值,涨跌幅,行业` returned 80 rows.

Use `上市天数(天)YYYY-MM-DD` when present; otherwise compute `days_since_listing` from ISO `上市日期`.

Observed `流通市值(日线不复权)YYYY-MM-DD` values are human strings such as `18.01亿`; parse with existing money helpers.

### Subsystem F — Capital Flow Slices (Tier 2 — scope-reduced)

**Why risky:** P5/P6 designed `pre_first_seal_5m / post_break_1m / tail_30m` windows assuming we'd have per-minute big-order net inflow. jvQuant's documented endpoints:

- Minute replay: time/last_price/volume/average_price (no big-order classification)
- Order queue (`mode=order_queue`): tick-level orders (premium endpoint)
- Capital flow at **day level**: visible in `资金流向` field of existing semantic queries

**Live finding:** Day-level semantic fields are available for `主力净额`, `超大单净额`, `大单净额`, `中单净额`, and `小单净额`. `order_book(600519, 0)` returns `offset`, `price`, `volume`, `type`, `time`, but this is not the same as semantic主力/散户 classification.

**Realistic path:** drop the original per-minute semantic capital-flow goal. Instead:

- Make `get_capital_flow_slices` return day-level net inflow for the symbol (one row, not 3 windows).
- Repurpose the `CapitalFlowSliceWindow` Literal to add `"daily"` and treat the existing 3 windows as Tier 3 (mock-only) until tick data justifies the cost.

This is a **scope reduction**, not full wiring. Document the reduction clearly in the SKILL workflow.

### Subsystem G — Dragon Tiger (Tier 1 raw, Tier 2 active seats)

**Probe result:** `今日龙虎榜,股票代码,股票简称,上榜原因,买入金额,卖出金额,净买入额` returned 97 rows on 2026-06-01. Top-level fields are `代码`, `名称`, and `龙虎榜YYYY-MM-DD`. The龙虎榜 value is nested and contains one or more list records with fields such as `上榜原因`, `买入额(元)`, `卖出额(元)`, `净买额(元)`, `龙虎榜榜单类型`, and `上榜原因解读`.

**P8 implementation:**

- `get_dragon_tiger(symbol, trading_day)` queries a raw龙虎榜 pool and filters by symbol.
- Parser flattens nested list records into `DragonTigerRecord` totals and `list_reason` notes.
- Tests cover a nested `龙虎榜YYYY-MM-DD` payload.

**Do not wire yet:**

- `get_active_seats_today` should stay placeholder until a probe exposes stable individual营业部 names or a separate alias source is introduced. The observed `营业部名称` query returned the same nested shape and did not demonstrate stable seat-level names.

## 5. Pre-Flight Checklist

Before implementation starts, the following must be true:

- [x] `.venv/bin/pip show jvquant` returns version info (SDK installed)
- [x] `JVQUANT_TOKEN` is set in `.env.local` (never committed)
- [x] `scripts/smoke_jvquant_readonly.py --symbol 600519 --timeout 30` runs cleanly (token + SDK working together)
- [x] Gap probes ran against live jvQuant on 2026-06-01
- [ ] User explicitly green-lights one or more implementation batches below
- [ ] At least 30 minutes of free API quota/time for the day if more probes are needed

## 6. Anti-Patterns to Avoid

If a future agent picks up this roadmap, these are the failure modes from P5/P6 that this document is trying to prevent:

1. **Don't write Chinese semantic queries from imagination.** Every query must come from a probe that returned actual data, captured in `docs/JVQUANT_FIELD_MAP.md`, `docs/JVQUANT_CAPABILITY_MATRIX.md`, or this roadmap's live-probe section.

2. **Don't hardcode field names.** Use `_first_field_value(row, "涨跌幅", "涨幅")` style fallbacks (existing pattern in `parsers.py`) so column renames don't silently break parsers.

3. **Don't claim `data_mode="real"` without an actual probe-confirmed query.** If the query was probe-confirmed but returned empty for a particular call, return empty list with `data_mode="real"`. If the endpoint itself wasn't confirmed, keep `data_mode="placeholder"`.

4. **Don't wire all 7 placeholders in one big-bang plan.** Each subsystem is a 2-4 task batch with its own probe + wire + test. Land one subsystem per phase if needed.

5. **Don't skip the probe sample as test fixture.** When you wire a parser, save 1-3 actual probe rows as a test fixture file (e.g. `tests/fixtures/jvquant_limit_down_2026-06-01.json`). This lets the test verify against real shape, not invented shape.

6. **Don't claim work is done if probe stayed empty.** Empty probe → placeholder stays. Document in `docs/JVQUANT_CAPABILITY_MATRIX.md` that the capability was probed and not found.

## 7. Trigger Conditions (When to Pick This Up)

Reasons to start executing this roadmap:

- User has time + token to run probes interactively
- Hermes use case where "channel = placeholder" is hurting the agent's ability to give a useful answer (e.g., user asks "is 章盟主 active today?" and the placeholder data forces a non-answer)
- User asks to replace placeholders that are now confirmed by live probes
- Account entitlement changes for queue/depth endpoints

Reasons NOT to start:

- "Cleanup phase" — placeholders aren't bugs; they're honest signals. Removing them isn't worth the risk if no real data source is ready.
- Pure architectural urge — refactoring placeholder method bodies without new capability is busywork.
- Without a token — pure code-only work will repeat P5/P6's mistake.

## 8. Estimated Effort (Rough)

Assuming all prerequisites met:

| Subsystem | Probe | Parser + wire | Tests | Total |
|-----------|-------|---------------|-------|-------|
| A. Weekly position | done | 4-6 hours | 1 hour | ~1 day |
| B. Limit-down pool | done | 2 hours | 30 min | ~half day |
| C. ST pool | done | 1 hour | 30 min | ~quarter day |
| D. Suspended stocks | done, empty result | 1-2 hours | 30 min | ~half day |
| E. New stock candidates | done | 2-3 hours | 1 hour | ~half day |
| F. Capital flow slices | done; scope reduced | 2-4 hours | 1 hour | ~1 day |
| G. Dragon Tiger raw record | done | 3-5 hours | 1 hour | ~1 day |
| H. Active seats | partial; needs more probe/source | unknown | unknown | separate follow-up |

Subsystems A-G, excluding active seats, are now realistic in ~3-4 focused days. Active seats remains separate because raw龙虎榜 does not yet prove stable营业部 alias extraction.

## 9. Implementation Plan Started

Recommended order:

1. **P8-A: low-risk confirmed fields** — completed: weekly position, limit-down pool, ST pool, and new-stock candidates.
2. **P8-B: confirmed-empty and raw nested data** — completed: suspended stocks as confirmed-empty capable, plus raw `get_dragon_tiger` with nested fixture coverage.
3. **P8-C: scope-reduced capital flow** — completed: contract supports a `"daily"` capital-flow slice while pre-seal/post-break/tail minute windows remain mock/derived-only.
4. **P8-D: active seats research** — not started: run a focused probe for individual营业部/席位 names. If no stable field appears, either keep placeholder or introduce an external alias/source plan.

## 10. What Belongs in This Document vs What Belongs in P8

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

Last updated: 2026-06-01 Asia/Shanghai — live jvQuant probes ran; P8 wired confirmed capabilities; active seats and minute-level semantic capital-flow slices remain pending.
