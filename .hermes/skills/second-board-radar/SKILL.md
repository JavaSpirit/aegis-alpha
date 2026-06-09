---
name: second-board-radar
description: Use when Hermes is asked to analyze A-share second-board candidates, one-to-two board setups, board-chasing market conditions, yesterday limit-up pools, theme co-movement, or Aegis Alpha MCP watchlist outputs. Guides Hermes to use Aegis Alpha read-only MCP tools with strict safety boundaries and no deterministic buy/sell instructions. The agent MUST walk all 5 factors per candidate and output a bucketed promotion_likelihood (high/medium/low) plus an agent-assigned grade (A/B/C/REJECT).
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
- Hermes: interpret the outputs, walk the 5 factors, assign `promotion_likelihood` and `grade`, explain tradeoffs, apply this skill, remember user preferences, and prepare review notes.
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
- `get_active_strategy_prior`
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
- `attribute_outcome`
- `get_history_stats`
- `run_backtest`
- `get_recent_backtests`
- `get_dragon_tiger`
- `get_active_seats_today`
- `get_limit_down_pool`
- `get_st_pool`
- `get_capital_flow_slices`
- `backfill_candidates`
- `find_similar_setups`
- `get_new_stock_candidates`
- `get_suspended_stocks`
- `query_minute_bars`
- `simulate_outcome`
- `detect_intraday_buypoint`

Useful supporting tools:

- `get_market_snapshot`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_orderbook_snapshot`
- `get_stock_history_limitup_stats`
- `review_candidate_outcome`
- `record_candidate_outcome`

`get_market_sentiment_gate` returns market FACTS — not an action label. Fields include: `limit_up_count`, `break_board_rate`, `hot_theme_count`, `risk_flags`, `positive_signals`, `conclusion`, `yesterday_limitup_today_premium_pct`, `consecutive_boards_alive_rate`, `first_to_second_promotion_rate`, `second_to_third_promotion_rate`, `max_height_today`. Do NOT treat these as gate commands; the AGENT reads the facts and makes its own environmental judgment.

If these tools are unavailable, first ask Hermes to reload MCP with `/reload-mcp` or inspect the Hermes MCP configuration. Do not fabricate live data.

## Data Availability And Freshness

If Aegis Alpha MCP times out, returns an error, or provides empty data, explicitly state `Data source unavailable` and halt candidate analysis. Do not guess, interpolate, or backfill missing speed, orderbook, big-order, or theme metrics.

Before grading during active trading hours, verify the timestamp of speed, big-order, and orderbook data. Active trading hours are 09:30-11:30 and 13:00-15:00 Asia/Shanghai. If any required realtime field is delayed by more than 3 minutes, cap the maximum grade at `B`, cap `promotion_likelihood` away from `high` (i.e. only `medium` or `low`), warn the user, and do not describe the candidate as high-confidence. If `five_min_speed_window` starts with `provider_exact_window:`, report that exact provider window; if it is `provider_latest_rolling_5m`, explain that the provider did not expose the exact five-minute start/end time.

If `five_min_speed_window` starts with `minute_replay_exact_window:` or `minute_replay_partial_window:`, state that Aegis Alpha recalculated the speed from jvQuant minute replay bars. Minute replay is minute-level replay data, not tick-by-tick realtime Level-2. During active trading hours, use `five_min_speed_timestamp` or `minute_replay_timestamp` to check freshness before grading.

For event-driven reviews, consume `MarketEvent` and `SignalSnapshot` outputs. Do not ask for raw WebSocket messages and do not infer from individual ticks. If an event has stale or unknown `freshness_status`, explain the event as low-confidence context rather than a live trigger.
Use `get_runner_status` when the user asks whether realtime monitoring is active. If the runner state is not `RUNNING`, do not describe Aegis Alpha as actively monitoring the market.

## Standard Workflow

1. Check the market sentiment gate before analyzing individual candidates. Call `get_market_sentiment_gate` and read the FACTS it returns: `limit_up_count`, `break_board_rate`, `hot_theme_count`, `risk_flags`, `positive_signals`, `conclusion`, `yesterday_limitup_today_premium_pct`, `consecutive_boards_alive_rate`, `first_to_second_promotion_rate`, `second_to_third_promotion_rate`, `max_height_today`. If these emotion fields are all zero with a note explaining they are placeholder, treat them as unavailable rather than as a cold-market signal.

2. From the market facts, make your own environmental judgment:
   - High `break_board_rate` (e.g. > 30%) and/or low `limit_up_count` and/or narrow `hot_theme_count` → environment is hostile; explain why, stay defensive, and do not pursue board-chasing candidates.
   - Moderate risk flags with some positive signals → cautious selective stance; highlight what would need to improve.
   - Low `break_board_rate`, healthy `limit_up_count`, broad `hot_theme_count`, positive `first_to_second_promotion_rate` or `consecutive_boards_alive_rate` → environment supports selective board-chasing.

3. If Aegis Alpha data is unavailable, stale beyond the freshness rule, or empty, follow the data availability rule before continuing.

4. If market facts support board-chasing (controlled break-board rate, sufficient limit-up breadth, at least one active hot theme), call `get_theme_leaders` and `get_market_emotion` for board-level context, then fetch second-board candidates with `get_second_board_candidates_compact`. Use `get_limit_up_ladder(symbol)` when you need to confirm a single stock's connect-board height; the candidate output already carries `previous_consecutive_boards`, `previous_height_label`, `theme_role`, and `theme_leader_symbol` so you usually do not need an extra call per candidate.

5. If Aegis Alpha returns recent market events, use them as context for re-scoring candidates, but do not treat event suggestions as order instructions.

6. For EACH candidate, you MUST walk all 5 factors explicitly. Do not produce only a general summary — 不得只给综合总结而跳过任一因子的逐项说明. The 5 required factors are:

   **Factor 1 — 市场情绪 (market_emotion)**: Derived from the market gate facts: `break_board_rate`, `limit_up_count`, `yesterday_limitup_today_premium_pct`, `first_to_second_promotion_rate`, `consecutive_boards_alive_rate`, `hot_theme_count`. State in one Chinese sentence what the market environment implies for this candidate's odds. Example: "涨停42家，炸板率18%，连板存活率62%，市场情绪较好，对二板进攻有支撑。"

   **Factor 2 — 题材所在位置 (theme_position)**: Read `theme_lifecycle_stage` from the candidate. The lifecycle stages are: `launch`(启动) → `fermenting`(发酵) → `climax`(高潮) → `divergence`(分歧) → `ebb`(退潮). CRITICAL RULE: if `theme_lifecycle_stage` is `divergence` or `ebb`, you MUST downweight the candidate even if recent hotness or limit-up rate looks superficially strong. This is because late-stage themes carry high reverse risk — the electric-power theme failure pattern (高位分歧题材仍强推二板) is a known failure mode that this rule is designed to catch. Use `theme_role`, `theme_leader_symbol`, and `get_top_themes_today` for corroboration.

   具体降权后果（不得例外，即使其他因子都强）：
   - `theme_lifecycle_stage=divergence` → grade 最高只能给 B，promotion_likelihood 最高只能 medium。
   - `theme_lifecycle_stage=ebb` → grade 必须 REJECT，promotion_likelihood 必须 low。
   - `theme_lifecycle_stage=climax`(高潮)：promotion_likelihood 最高只能 medium，除非量能与回封力度同时很强，才可给 high。climax 阶段是分歧前的最后一档，高潮期兑现风险高，必须在因子说明里点出。

   **Factor 3 — 股本大小 (float_size)**: Use `free_float_market_cap_cny`. Large float reduces the probability of sustained sealing; small float with strong theme is favorable. State the float size and its implication in one Chinese sentence.

   **Factor 4 — 量能与资金 (volume_energy)**: Use `avg_turnover_10d_cny` (10-day average volume baseline), `ma5_slope_degrees` (price trend slope), `prev_day_volume_shrink_ratio` (whether yesterday shrank vs. prior days — a high ratio means volume dried up), and `broke_previous_high` (whether price cleared the prior swing high). ALSO cover `big_order_net_inflow_ratio` (net big-order inflow as a proportion of turnover — positive means institutional accumulation, negative means distribution) and `orderbook_quality_score` (queue depth and composition quality). An A-grade requires positive big-order inflow AND strong orderbook quality; if either is missing or negative, cap the assessment at B. State the overall volume-and-capital picture in one or two Chinese sentences. Note: the JSON output field key MUST remain `volume_energy` (the validator checks that exact key).

   **Factor 5 — 回封力度 (reseal_strength)**: Use `break_board_count`, `reseal_count`, `max_seal_amount_cny`, `final_seal_time`, and `seal_to_turnover_ratio`. A high `break_board_count` with fast, large `reseal_count` and strong `max_seal_amount_cny` suggests genuine institutional intent to hold the board. A `final_seal_time` near market close with a high `seal_to_turnover_ratio` is a positive sign. State the reseal pattern in one Chinese sentence.

7. After walking all 5 factors, assign `promotion_likelihood` and `grade`:
   - `promotion_likelihood`: MUST be exactly one of `high` / `medium` / `low`. This represents the bucketed probability of this candidate progressing to the third board (三板). The program validates this field — do not use a decimal, percentage, or any other format.
   - `grade`: YOUR judgment as the analyst — exactly one of `A`, `B`, `C`, or `REJECT`. This is not produced by the program; the agent assigns it based on the full picture.
   - 一般对应关系：A→high、B→medium、C/REJECT→low。若 grade 与 promotion_likelihood 出现反差（如 grade=A 但 promotion_likelihood=low），必须在评级原因里明确解释反差原因，不得无声矛盾。

8. Produce a watchlist report. For each candidate, the agent assigns the grade and explains the reason. Always include structured trigger conditions and avoid conditions.

9. Always state both model identity and market-data identity. Keep `llm_provider` / `llm_model` separate from `market_data_mode` / `market_data_provider`.

10. After every candidate, explain the reasoning in natural Chinese, synthesized from the 5 factors. Do not rely on any program-emitted `grade_reason` field — the program no longer produces one. Always derive the reason yourself from the returned metrics.

11. Use the full `get_second_board_candidates` only when the compact output is insufficient. If evidence details are needed, prefer `get_second_board_candidate_data_quality(symbol)` over fetching the full candidate pool again, to avoid tool-output truncation.

12. For multi-hour monitoring, create a watchlist with `create_watchlist(owner=user, label=YYYY-MM-DD label, symbols=A|B|C)` early in the session. Use `update_watchlist_state(watchlist_id, symbol, new_grade, action, note)` whenever a candidate's grade changes during the day. Use `close_watchlist(watchlist_id, note)` at session end to seal the audit trail. List existing watchlists with `list_active_watchlists(owner)`.

13. Read `get_pending_alerts(limit)` whenever the user starts a new chat to surface anything the runner detected while away. After acting on an alert call `acknowledge_alert(alert_id, note)`. The runner persists alerts for `SEAL_ORDER_DECAY`, `BIG_ORDER_INFLOW_SPIKE`, and `THEME_DIVERGENCE` events; do not re-run the same analysis if the alert is still pending.

14. After 15:10, run `generate_daily_review(trading_day=today)` to produce the structured review item used by Phase 3 review-and-correction. For weekly pattern audits use `generate_weekly_pattern_report(start_day, end_day)` (max 14-day window recommended).

15. Use `get_top_themes_today(trading_day, limit)` to surface the leading themes ranked by member count and leader connect-board height, and `get_seal_timeline(symbol)` to inspect intraday seal/break events when a candidate's `theme_role` shows `co_leader` or `follower`.

16. After collecting at least 5 trading days of outcomes, run `attribute_outcome(symbol, trading_day)` for failed candidates to identify recurring failure patterns. Surface the top primary_tag from recent attributions as a Hermes memory candidate after 3+ similar tags accumulate.

17. Use `get_history_stats(symbol)` instead of relying on the placeholder three_year_* fields when available. If `confidence` is `insufficient_sample`, treat the historical signal as unavailable and do not narrate a probability.

18. When the user asks "would tightening rule X improve hit rate?", call `run_backtest(rule_changes_json, start_day, end_day)` and report the sealed_rate delta and advice. Never apply a threshold proposal automatically — they always require the human-confirmation flow defined by `record_correction_action_decision`. Note: the threshold-backtest tool is currently being re-homed (Phase 7) and returns unavailable for certain rule change types; do not rely on it until it is re-enabled.

19. P5 数据维度可选用：
    - `get_dragon_tiger(symbol, trading_day)` 在收盘后查看候选股的龙虎榜结构；如席位含 `hot_money_known` 且 `hot_money_alias` 为白名单游资（章盟主、孙哥等），在评级原因里点出资金主体。
    - `get_active_seats_today(trading_day)` 看当天哪几位游资同时进入多只股，用作板块共振辅助证据。
    - `get_limit_down_pool(trading_day)` / `get_st_pool(trading_day)` 在判断市场情绪时观察反向池规模；如 `MARKET_BOTTOM_REVERSAL` 事件出现，将其当作板块见底的辅助语境，不要由它直接推荐买点。
    - 候选契约里 `limitup_driver_type` 与 `intraday_pattern` 在 evidence 里给一句中文备注；`policy` / `earnings` 驱动通常比 `theme` 更稳，`one_word_board` / `platform_breakout` 比 `messy_board` / `false_breakout` 风险更低。
    - `get_capital_flow_slices(symbol, trading_day)` 在复盘失败案例时使用：`tail_30m` 主力净流出说明尾盘机构离场。

20. P4 盘中买点离线回放（Phase 4，按需使用）：
    - `detect_intraday_buypoint(symbol, end_day, previous_high)` 返回盘中买点形态的离线回放告警（过前高→回踩缩量→重新上冲）。这是研究告警，不是下单指令。当前为离线历史回放（实盘盘中监控是后续阶段）；阈值用默认值，策略 prior（后续阶段）会让 30-60° 斜率 / 均量 > 50 亿等阈值可切换。把返回的 `signals` 当作观察证据，结合五因子判断，不要据此直接下单。若未传 `previous_high`，工具会用开盘前 3 根 bar 的最高 `last_price` 作为保守替代；传入明确前高更准确。

21. P6 进阶能力（按需使用）：
    - `find_similar_setups(symbol, lookback_days, similarity_threshold)` 在复盘候选时找相似历史样本；当返回的 `similarity ≥ 0.85`，可作为「这个形态历史上确实经常打成功」的弱证据，但不要替代当下行情判断。注意：历史快照的 agent/human 评级（若有记录）为弱参考，若为 None 则完全忽略。
    - `get_new_stock_candidates()` 返回的 `tier_aged_out` 不应再按次新处理；`tier_a_smallcap_recent` 才是典型的次新打板候选。
    - `get_suspended_stocks(trading_day)` 在每次拉候选前检查；候选若出现在停牌列表中应直接 REJECT 并提示数据脏。
    - `query_minute_bars(symbol, start_day, end_day)` 仅在 history-store extras 安装后可用；返回 `data_mode=unavailable` 时直接告诉用户分钟级历史层未启用。
    - `simulate_outcome(symbol, trading_day, hypothesis_json)` 在用户问「如果当时封单是 X 亿，评级会变吗？」时调用；返回 `payload_diff` 是结构化对比，不是确定性结论。P8 起它会用真 `candidate_grade()` 重算：你可以传任意 `{"action": "avoid"}` / `{"orderbook_quality_score": 80.0}` 等覆盖来观察 `hypothetical_grade` 变化。
    - 候选契约里的 `weekly_health_score` ≥ 70 表示周线位置健康，可加分；< 30 应在评级原因里点出周线劣势。
    - 板块事件 `THEME_LEADER_BREAK_BOARD`（高度龙头炸板）与 `SECTOR_ROTATION`（板块轮动）：当 `get_recent_market_events` 返回这两类事件时，把它们当作板块级风险/机会语境而不是单股触发——前者意味着同题材 follower 应整体降级，后者意味着可以把注意力从 weakening_theme 转向 strengthening_theme 的 followers。P8 起，板块事件 `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION` / `MARKET_BOTTOM_REVERSAL` 会触发 runner macOS 告警；通过 `get_pending_alerts(limit)` 拉到的告警里会带这 3 类。
    - 停牌过滤已在 P7 自动接入候选拉取链路 — 候选列表中不会再出现停牌股；如人工手动评估某只票，仍可调 `get_suspended_stocks(trading_day)` 复核。
    - `simulate_outcome` 的 `hypothetical_grade` 现在来自完整 candidate_grade 重算，不再受限于 P7 的 `seal_amount_cny` / `five_min_speed_pct` 两字段启发。

## Strategy Prior

Call `get_active_strategy_prior` once per session to load the active strategy prior (currently `client_10pt` — 客户口述的二板买点策略). The prior is **GUIDANCE, not a filter**. It carries soft ideal ranges and qualitative notes the client cares about. The program never accepts or rejects a candidate based on the prior; YOU weigh each candidate's measured facts against the prior and decide.

How to use it:

- **Soft ranges (`thresholds`)**: each threshold has `ideal_low`/`ideal_high`/`unit`/`rationale`. Compare the candidate's measured fact to the ideal range and report the comparison in your factor write-up. Current ranges: 近10日均成交量 ideal ≥ 50亿 (`avg_turnover_10d`); 5日均线斜率 ideal 30–60° (`ma5_slope_degrees`).
- **Override-with-reasoning (MANDATORY)**: a candidate OUTSIDE a prior's ideal range is NOT auto-rejected. If facts justify it, keep the candidate and state the override explicitly — e.g. "5日斜率 72°，超出先验 30–60° 区间，但题材处于发酵期且回封力度强，故仍保留为 B，理由：……". Likewise, being INSIDE every range does NOT guarantee a high grade — the 5-factor judgment still governs. Never treat a prior range as a pass/fail gate.
- **Guidance notes (`guidance_notes`)**: qualitative items to weave into your reasoning — 板块两周持续性（可能需你做盘外信息确认）、T-1 缩量、T 日带量过前高、回踩缩量后重新上冲=买入预警点、同板块共振加分、重点监控时段 9:30–9:50 与 11:10–11:30。
- **板块两周持续性** is an agent task GUIDED by the prior: when the prior flags it, you should seek out-of-platform corroboration (盘外抓取) of whether the sector has shown repeated multi-day strength over the past two weeks, and say so — do not fabricate it if you cannot confirm.
- **财联社消息**: `caixin_alignment` is a placeholder this cycle (本期暂不接入财联社消息源). Do not claim a 财联社 alignment signal exists; treat it as not-yet-available.

If `get_active_strategy_prior` returns `data_mode: unavailable`, proceed with the standard 5-factor workflow without the prior and note that no active prior was loaded.

## Candidate Interpretation Rules

Use these as agent grading heuristics unless the user's memory or the Aegis Alpha output provides specific guidance:

- `A`: market facts indicate a supportive environment (low break-board rate, sufficient limit-up breadth, positive promotion rates); same-theme co-movement is strong; `theme_lifecycle_stage` is `launch` or `fermenting` (climax 见下方天花板规则); orderbook quality is strong; big-order inflow is positive; volume energy shows expansion; reseal strength is convincing; historical stats are favorable.
- `B`: watch closely, but at least one important factor is not ideal — including but not limited to volume shrinkage, mixed market breadth, or climax-stage theme risk. `theme_lifecycle_stage=divergence` 总是把 grade 限制在 B（即使其他因子都强）。
- `C`: observation only; do not frame it as actionable.
- `REJECT`: not in yesterday's valid limit-up pool; market-wide break-board rate is high and breadth is collapsing (agent's judgment from facts); theme leader broke board; `theme_lifecycle_stage=ebb`（退潮阶段一律 REJECT，不论封单多大）; or data quality is insufficient.

If speed, big-order, or orderbook timestamps are delayed by more than 3 minutes during active trading hours, maximum grade is `B` and `promotion_likelihood` must not be `high`.

For second-board analysis, prefer fewer candidates with better explanation over broad lists.

## Output Format

Use this structure for user-facing answers. The `factor_analysis` block and `promotion_likelihood` are MANDATORY for every candidate. Omitting any factor or replacing the factor walk with a general summary is a violation of this skill's contract.

```text
市场环境(事实): 涨停N家 炸板率X% 连板存活率Y% 热门题材M个 → 判断: 适合/谨慎/不宜进攻

候选:
1. 代码 名称
   晋级三板概率(分档): high / medium / low
   综合评级(agent): A / B / C / REJECT
   因子分析:
   - 市场情绪: <一句中文说明，基于涨停数/炸板率/溢价率等市场事实>
   - 题材所在位置: <说明 theme_lifecycle_stage 及其含义；若为 divergence/ebb 须明确点出降权原因>
   - 股本大小: <说明 free_float_market_cap_cny 及对封板持续性的影响>
   - 量能: <说明 avg_turnover_10d_cny / ma5_slope_degrees / prev_day_volume_shrink_ratio / broke_previous_high / big_order_net_inflow_ratio / orderbook_quality_score>
   - 回封力度: <说明 break_board_count / reseal_count / max_seal_amount_cny / final_seal_time / seal_to_turnover_ratio>
   评级原因: <综合五个维度的自然语言总结，说明主要加分项和主要扣分项>
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
- Never ignore the market sentiment gate facts.
- Never recommend board-chasing when market-wide break-board rate is high or limit-up breadth is collapsing (agent's judgment from facts).
- Never analyze arbitrary symbols as second-board candidates unless they are in the valid previous-day limit-up pool or the user explicitly asks for a hypothetical review.
- If data is stale, missing, or inconsistent, downgrade confidence and say so.
- A strategy prior is guidance only: never apply a prior's range as a hard pass/fail filter, and never let a prior override measured facts — facts win, and any deviation from the prior must be stated with reasoning.

## Review And Memory

When the user corrects a judgment, summarize the reusable lesson and ask whether to remember it.
Use `record_candidate_outcome` for explicit review facts or user corrections; do not store rumors, credentials, or unverified tips as outcomes.

Good memory candidates:

- The user prefers second-board setups over first-board setups.
- The user dislikes fast boards without theme co-movement.
- The user wants less activity when break-board rate is high.
- The user cares about next-day open and third-day premium after sealed second boards.
- Late-stage themes (`divergence`/`ebb`) should be downweighted even if short-term hotness looks strong (电力题材高位失败教训).

Do not save raw stock tips, credentials, or one-off market rumors as memory.

## Scheduled Use

For Hermes cron jobs, prompts must be self-contained. A useful schedule is:

- 09:20: prepare yesterday-limit-up pool and market precheck.
- 09:30-10:30: monitor the second-board candidate list.
- 15:10: review whether candidates touched limit-up, sealed, broke board, and produced expected follow-through.

Cron outputs should be concise and should not claim real-time monitoring unless the MCP data source is live.
