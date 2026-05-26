---
name: second-board-radar
description: Use when Hermes is asked to analyze A-share second-board candidates, one-to-two board setups, board-chasing market sentiment, yesterday limit-up pools, theme co-movement, or Aegis Alpha MCP watchlist outputs. Guides Hermes to use Aegis Alpha read-only MCP tools with strict safety boundaries and no deterministic buy/sell instructions.
license: Proprietary
metadata:
  hermes:
    tags: [Trading, A-share, Second Board, MCP, Risk]
    related_skills: []
    config:
      - key: aegis_alpha.workspace
        description: Absolute path to the Aegis Alpha repository.
        default: "/Users/xietian/Documents/trading"
        prompt: Aegis Alpha workspace path
---

# Second-Board Radar

This skill is for research, watchlist, and review workflows only. Do not issue deterministic buy or sell instructions. Do not call or invent trading execution tools. Do not ask the user for broker credentials.

Market-data provider selection and secrets belong to the Aegis Alpha MCP server configuration, not to this skill. If live data is unavailable, report the unavailable state and continue only with mock or documented stale data.

## Operating Model

Aegis Alpha provides structured data and rule outputs through MCP. Hermes provides reasoning, explanation, memory, and review.

The correct division of responsibility is:

- Aegis Alpha MCP: data access, scoring inputs, timestamps, provider state, and deterministic signal contracts.
- Hermes: interpret the outputs, explain tradeoffs, apply this skill, remember user preferences, and prepare review notes.
- Human user: final decision.
- Future risk engine: required before any paper or real order workflow.

## Required MCP Tools

Prefer Aegis Alpha MCP tools. Hermes may expose them with a server prefix such as `mcp_aegis_alpha_`.

Core tools:

- `get_market_sentiment_gate`
- `get_second_board_candidates`
- `explain_second_board_candidate`
- `get_stock_realtime_snapshot`
- `get_theme_strength`

Useful supporting tools:

- `get_market_snapshot`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_orderbook_snapshot`
- `get_stock_history_limitup_stats`

If these tools are unavailable, first ask Hermes to reload MCP with `/reload-mcp` or inspect the Hermes MCP configuration. Do not fabricate live data.

## Data Availability And Freshness

If Aegis Alpha MCP times out, returns an error, or provides empty data, explicitly state `Data source unavailable` and halt candidate analysis. Do not guess, interpolate, or backfill missing speed, orderbook, big-order, or theme metrics.

Before grading during active trading hours, verify the timestamp of speed, big-order, and orderbook data. Active trading hours are 09:30-11:30 and 13:00-15:00 Asia/Shanghai. If any required realtime field is delayed by more than 3 minutes, cap the maximum grade at `B`, warn the user, and do not describe the candidate as high-confidence.

## Standard Workflow

1. Check the market sentiment gate before analyzing individual candidates.
2. If the gate action is `avoid`, say the environment is unsuitable for board-chasing and stop at a defensive market summary.
3. If the gate action is `defensive`, only discuss why risk is elevated and list what would need to improve.
4. If Aegis Alpha data is unavailable, stale beyond the freshness rule, or empty, follow the data availability rule before continuing.
5. If the gate action is `selective` or `active`, fetch second-board candidates.
6. For each candidate, analyze only the structured signals returned by Aegis Alpha:
   market gate, five-minute speed, big-order net inflow ratio, same-theme rising count, orderbook quality, historical touch-limit success rate, and historical gap-up statistics.
7. Produce a watchlist report with grades `A`, `B`, `C`, or `REJECT`.
8. Always include structured trigger conditions and avoid conditions.
9. Always state both model identity and market-data identity. Keep `llm_provider` / `llm_model` separate from `market_data_mode` / `market_data_provider`.

## Candidate Interpretation Rules

Use these defaults unless the user's memory or the Aegis Alpha output says otherwise:

- `A`: market gate is active or selective; same-theme co-movement is strong; orderbook quality is strong; big-order inflow is positive; historical stats are favorable.
- `B`: watch closely, but at least one important dimension is not ideal.
- `C`: observation only; do not frame it as actionable.
- `REJECT`: not in yesterday's valid limit-up pool, market gate is avoid, theme leader broke board, or data quality is insufficient.

If speed, big-order, or orderbook timestamps are delayed by more than 3 minutes during active trading hours, maximum grade is `B` even if other signals look strong.

For second-board analysis, prefer fewer candidates with better explanation over broad lists.

## Output Format

Use this structure for user-facing answers:

```text
市场闸门: active/selective/defensive/avoid
结论: ...

候选:
1. 代码 名称 评级
   观察:
   风险:
   触发条件:
   - 价格: ...
   - 量能/大单: ...
   - 板块动作: ...
   禁止条件:
   - 价格: ...
   - 量能/盘口: ...
   - 板块动作: ...

数据状态:
- llm_provider:
- llm_model:
- market_data_mode:
- market_data_provider:
非投资建议:
```

Examples of concrete avoid conditions include: high open below 3%, auction front-running, same-theme leader breaking the intraday VWAP, orderbook quality falling below threshold, big-order net inflow turning negative, or break-board rate expanding quickly.

Do not write "buy", "must buy", "sell", "full position", or "guaranteed". Use "观察", "候选", "触发条件", "禁止条件", and "风险".

## Safety Rules

- Never request or expose broker credentials, trading passwords, or real order tokens.
- Never propose real automated trading from this skill.
- Never treat mock data as real market data.
- Never ignore the market sentiment gate.
- Never recommend board-chasing when the gate action is `avoid`.
- Never analyze arbitrary symbols as second-board candidates unless they are in the valid previous-day limit-up pool or the user explicitly asks for a hypothetical review.
- If data is stale, missing, or inconsistent, downgrade confidence and say so.

## Review And Memory

When the user corrects a judgment, summarize the reusable lesson and ask whether to remember it.

Good memory candidates:

- The user prefers second-board setups over first-board setups.
- The user dislikes fast boards without theme co-movement.
- The user wants less activity when break-board rate is high.
- The user cares about next-day open and third-day premium after sealed second boards.

Do not save raw stock tips, credentials, or one-off market rumors as memory.

## Scheduled Use

For Hermes cron jobs, prompts must be self-contained. A useful schedule is:

- 09:20: prepare yesterday-limit-up pool and market precheck.
- 09:30-10:30: monitor the second-board candidate list.
- 15:10: review whether candidates touched limit-up, sealed, broke board, and produced expected follow-through.

Cron outputs should be concise and should not claim real-time monitoring unless the MCP data source is live.
