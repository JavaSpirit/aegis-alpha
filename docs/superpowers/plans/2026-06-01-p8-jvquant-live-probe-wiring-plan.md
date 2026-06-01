# P8 Plan: jvQuant Live-Probe Wiring

> **Status: COMPLETE for Batches A-C.** This plan started from the live probe evidence captured in `docs/superpowers/plans/2026-06-01-future-jvquant-real-integration-roadmap.md`. Confirmed jvQuant capabilities are now wired; active-seat alias aggregation remains a separate research batch.

## Goal

Replace jvQuant placeholders that now have live-observed field shapes, while preserving honest `placeholder` / derived-data warnings for capabilities that are still partial.

## Evidence Baseline

Live probes ran on 2026-06-01 23:39 Asia/Shanghai with `jvquant==1.20.5` and a real token from `.env.local`. Confirmed usable:

- Weekly K-line: `client.kline(symbol, "stock", "前复权", "week", 12)`
- Limit-down pool: `今日跌停,...`
- ST pool: `是否ST=是,...`
- New-stock candidates: `上市天数小于180,...`, `次新股,...`, date filter
- Suspended-stock fields: confirmed, but count 0 on probe day
- Dragon Tiger raw records: nested `龙虎榜YYYY-MM-DD`
- Daily capital flow: `主力净额`, `超大单净额`, `大单净额`, `中单净额`, `小单净额`

Still partial or blocked:

- `get_active_seats_today`: raw龙虎榜 exists, but stable individual营业部 names were not observed.
- Original minute-level capital-flow windows: no observed semantic主力/散户 decomposition.
- `level_queue`: current account hit a quota/points limitation.

## Batch A — Low-Risk Confirmed Fields

**Status: complete.**

**Scope:** `get_weekly_position`, `get_limit_down_pool`, `get_st_pool`, `get_new_stock_candidates`.

1. Add parser helpers under `src/aegis_alpha/adapters/jvquant/` or reuse `parsers.py` patterns:
   - `parse_weekly_position_payload(week_payload, day_payload, symbol)`
   - `parse_limit_down_pool_payload(payload, trading_day)`
   - `parse_st_pool_payload(payload, trading_day)`
   - `parse_new_stock_candidates_payload(payload, today)`
2. Wire adapter methods in `src/aegis_alpha/adapters/jvquant/adapter.py`.
3. Replace placeholder tests in:
   - `tests/extensions/test_weekly_position.py`
   - `tests/extensions/test_contrarian_pool.py`
   - `tests/extensions/test_new_stocks.py`
4. Add observed-shape fixtures or inline fake payloads that exactly use probe fields.

Acceptance:

- [x] No real network calls in unit tests.
- [x] Placeholder assertions are replaced with real parser/adapter assertions.
- [x] `data_mode` is `live_provider`, not `placeholder`.
- [x] `-` values from ST rows are treated as missing in notes rather than silently trusted as numeric data.

## Batch B — Confirmed-Empty and Nested Data

**Status: complete.**

**Scope:** `get_suspended_stocks`, `get_dragon_tiger`.

1. Add `parse_suspended_stocks_payload(payload, trading_day)`.
2. Wire `get_suspended_stocks` so confirmed empty results return `[]` as real data, not placeholder.
3. Add `parse_dragon_tiger_payload(payload, symbol, trading_day)` for nested `龙虎榜YYYY-MM-DD`.
4. Wire `get_dragon_tiger` using a pool query plus symbol filter first; only add a symbol-specific query after another probe confirms it.
5. Update tests in:
   - `tests/extensions/test_suspended_stocks.py`
   - `tests/extensions/test_dragon_tiger.py`

Acceptance:

- [x] Suspended-stock tests cover both observed empty payload and one synthetic field-compatible row.
- [x] Dragon Tiger tests flatten nested records and sum buy/sell/net values from human money strings.
- [x] `get_active_seats_today` remains placeholder with a clearer note that raw龙虎榜 is available but seat alias extraction is not confirmed.

## Batch C — Scope-Reduced Daily Capital Flow

**Status: complete.**

**Scope:** `get_capital_flow_slices`.

1. Update `CapitalFlowSliceWindow` to include `"daily"` if the current model contract allows it cleanly.
2. Add a daily parser for semantic fields:
   - `主力净额`
   - `超大单净额`
   - `大单净额`
   - `中单净额`
   - `小单净额`
3. Wire `get_capital_flow_slices(symbol, trading_day)` to return one daily slice.
4. Keep `pre_first_seal_5m`, `post_break_1m`, and `tail_30m` as mock-only / derived-only until a separate contract is approved.

Acceptance:

- [x] The method does not claim minute-level real主力 flow.
- [x] Notes explicitly say daily semantic capital flow, not tick-by-tick Level2 classification.
- [x] Existing mock behavior remains valid.

## Batch D — Active Seats Research

**Status: not started; intentionally excluded from this implementation.**

**Scope:** more probes only.

Probe candidates:

- `今日龙虎榜,营业部,股票代码,股票简称,买入金额,卖出金额,净买入额`
- `今日龙虎榜,买入营业部,卖出营业部,股票代码,股票简称,买入金额,卖出金额,净买入额`
- Symbol-specific龙虎榜 query for one known row from the 2026-06-01 probe

Decision:

- If stable seat names appear, add a parser and alias map plan.
- If only summarized `上榜原因解读` appears, keep `get_active_seats_today` placeholder and document the limitation.

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q`
- Result: `325 passed, 2 skipped, 1 warning`
