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
        description: Absolute path to the Aegis Alpha repository (your local checkout).
        default: ""
        prompt: Aegis Alpha workspace path (absolute path to your local clone)
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
- `get_market_emotion`
- `get_theme_leaders`
- `get_top_themes_today`
- `get_limit_up_ladder`
- `get_auction_analysis`
- `get_seal_timeline`
- `get_second_board_candidates_compact`
- `get_second_board_candidates`
- `get_second_board_candidate_data_quality`
- `explain_second_board_candidate`
- `get_stock_realtime_snapshot`
- `get_stock_minute_replay_snapshot`
- `get_recent_market_events`
- `get_signal_snapshot`
- `get_event_scoring_config`
- `get_realtime_connection_status`
- `get_runner_status`
- `explain_market_event`
- `get_theme_strength`
- `create_watchlist`
- `update_watchlist_state`
- `close_watchlist`
- `list_active_watchlists`
- `get_pending_alerts`
- `acknowledge_alert`
- `generate_daily_review`
- `generate_weekly_pattern_report`

Useful supporting tools:

- `get_market_snapshot`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_orderbook_snapshot`
- `get_stock_history_limitup_stats`
- `review_candidate_outcome`
- `record_candidate_outcome`

If these tools are unavailable, first ask Hermes to reload MCP with `/reload-mcp` or inspect the Hermes MCP configuration. Do not fabricate live data.

## Data Availability And Freshness

If Aegis Alpha MCP times out, returns an error, or provides empty data, explicitly state `Data source unavailable` and halt candidate analysis. Do not guess, interpolate, or backfill missing speed, orderbook, big-order, or theme metrics.

Before grading during active trading hours, verify the timestamp of speed, big-order, and orderbook data. Active trading hours are 09:30-11:30 and 13:00-15:00 Asia/Shanghai. If any required realtime field is delayed by more than 3 minutes, cap the maximum grade at `B`, warn the user, and do not describe the candidate as high-confidence. If `five_min_speed_window` starts with `provider_exact_window:`, report that exact provider window; if it is `provider_latest_rolling_5m`, explain that the provider did not expose the exact five-minute start/end time.

If `five_min_speed_window` starts with `minute_replay_exact_window:` or `minute_replay_partial_window:`, state that Aegis Alpha recalculated the speed from jvQuant minute replay bars. Minute replay is minute-level replay data, not tick-by-tick realtime Level-2. During active trading hours, use `five_min_speed_timestamp` or `minute_replay_timestamp` to check freshness before grading.

For event-driven reviews, consume `MarketEvent` and `SignalSnapshot` outputs. Do not ask for raw WebSocket messages and do not infer from individual ticks. If an event has stale or unknown `freshness_status`, explain the event as low-confidence context rather than a live trigger.
Use `get_runner_status` when the user asks whether realtime monitoring is active. If the runner state is not `RUNNING`, do not describe Aegis Alpha as actively monitoring the market.

## Standard Workflow

1. Check the market sentiment gate before analyzing individual candidates. The gate now exposes `consecutive_boards_alive_rate`, `first_to_second_promotion_rate`, `second_to_third_promotion_rate`, `yesterday_limitup_today_premium_pct`, and `max_height_today` directly — read these before drilling into candidates. If these emotion fields are all zero with a note explaining they are placeholder, treat them as unavailable rather than as a cold-market signal.
2. If the gate action is `avoid`, say the environment is unsuitable for board-chasing and stop at a defensive market summary.
3. If the gate action is `defensive`, only discuss why risk is elevated and list what would need to improve.
4. If Aegis Alpha data is unavailable, stale beyond the freshness rule, or empty, follow the data availability rule before continuing.
5. If the gate action is `selective` or `active`, call `get_theme_leaders` and `get_market_emotion` for board-level context, then fetch second-board candidates with `get_second_board_candidates_compact`. Use `get_limit_up_ladder(symbol)` when you need to confirm a single stock's connect-board height; the candidate output already carries `previous_consecutive_boards`, `previous_height_label`, `theme_role`, and `theme_leader_symbol` so you usually do not need an extra call per candidate.
6. If Aegis Alpha returns recent market events, use them as context for re-scoring candidates, but do not treat event suggestions as order instructions.
7. For each candidate, analyze only the structured signals returned by Aegis Alpha:
   market gate, auction metrics (including `auction_pattern` from `get_auction_analysis` when needed), connect-board ladder (`previous_consecutive_boards`, `previous_height_label`), theme role (`theme_role`, `theme_leader_symbol`), 1/3/5/10-minute speed structure, big-order net inflow ratio, concept/topic tags, first/final limit-up time, seal amount, max seal amount, seal-to-turnover ratio, break/reseal count, queue position note, same-theme rising count, orderbook quality, historical touch-limit success rate, and historical gap-up statistics. Reject board-chasing on a `follower` when its theme leader has broken board.
8. Produce a watchlist report with grades `A`, `B`, `C`, or `REJECT`.
9. Always include structured trigger conditions and avoid conditions.
10. Always state both model identity and market-data identity. Keep `llm_provider` / `llm_model` separate from `market_data_mode` / `market_data_provider`.
11. After every candidate grade, explain the reason in natural Chinese. Prefer the MCP `grade_reason` field when present; if it is absent, synthesize one from the returned metrics without inventing missing data.
12. Use the full `get_second_board_candidates` only when the compact output is insufficient. If evidence details are needed, prefer `get_second_board_candidate_data_quality(symbol)` over fetching the full candidate pool again, to avoid tool-output truncation.
13. For multi-hour monitoring, create a watchlist with `create_watchlist(owner=user, label=YYYY-MM-DD label, symbols=A|B|C)` early in the session. Use `update_watchlist_state(watchlist_id, symbol, new_grade, action, note)` whenever a candidate's grade changes during the day. Use `close_watchlist(watchlist_id, note)` at session end to seal the audit trail. List existing watchlists with `list_active_watchlists(owner)`.
14. Read `get_pending_alerts(limit)` whenever the user starts a new chat to surface anything the runner detected while away. After acting on an alert call `acknowledge_alert(alert_id, note)`. The runner persists alerts for `SEAL_ORDER_DECAY`, `BIG_ORDER_INFLOW_SPIKE`, and `THEME_DIVERGENCE` events; do not re-run the same analysis if the alert is still pending.
15. After 15:10, run `generate_daily_review(trading_day=today)` to produce the structured review item used by Phase 3 review-and-correction. For weekly pattern audits use `generate_weekly_pattern_report(start_day, end_day)` (max 14-day window recommended).
16. Use `get_top_themes_today(trading_day, limit)` to surface the leading themes ranked by member count and leader connect-board height, and `get_seal_timeline(symbol)` to inspect intraday seal/break events when a candidate's `theme_role` shows `co_leader` or `follower`.

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
   评级原因: 用一两句自然语言说明为什么是这个评级，必须点名主要加分项和主要扣分项。
   竞价数据: auction_change_pct / auction_turnover_cny / auction_turnover_rate
   涨速数据: five_min_speed_pct / five_min_speed_window / five_min_speed_timestamp / data_quality.five_min_speed
   分时回放: minute_replay_trading_day / minute_replay_bar_count / minute_replay_timestamp
   题材数据: concept_tags / topic_tags
   证据层级: official_doc / observed_probe / internal_inference 中实际出现的 authority
   封板数据: 首次封板时间 / 最终封板时间 / 封单额 / 最大封单额 / 炸板次数 / 回封次数 / 封成比 / 排队位置说明
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
Use `record_candidate_outcome` for explicit review facts or user corrections; do not store rumors, credentials, or unverified tips as outcomes.

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
