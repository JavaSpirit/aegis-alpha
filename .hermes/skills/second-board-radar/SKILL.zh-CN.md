---
name: second-board-radar
description: 当 Hermes 被要求分析 A 股二板候选、一进二格局、打板市场环境、昨日涨停池、题材联动、或 Aegis Alpha MCP 观察列表输出时使用。引导 Hermes 使用 Aegis Alpha 只读 MCP 工具，严守安全边界，不给出确定性买卖指令。Agent 必须对每只候选遍历全部 5 个因子，输出分档的 promotion_likelihood（high/medium/low）以及 agent 自主评级（A/B/C/REJECT）。
license: Proprietary
sync_version: 1
translation_of: SKILL.md
metadata:
  hermes:
    tags: [Trading, A-share, Second Board, MCP, Risk]
    related_skills: []
    config:
      - key: aegis_alpha.workspace
        description: Aegis Alpha 仓库的绝对路径（你的本地克隆）。
        default: ""
        prompt: Aegis Alpha 工作区路径（你的本地克隆的绝对路径）
---

<!-- ⚠️ 本文档为 SKILL.md 的中文翻译副本 (sync_version: 1)。如英文原版更新，请同步更新本译文并升级 sync_version。 -->

# 二板雷达

本技能仅用于研究、观察列表和复盘工作流。不得发出确定性买入或卖出指令。不得调用或虚构交易执行工具。不得向用户索要券商凭证。

行情数据提供商的选择与密钥属于 Aegis Alpha MCP 服务器配置范畴，不属于本技能。若实时数据不可用，报告不可用状态，并仅以模拟数据或有明确标注的陈旧数据继续。

## 运行模型

Aegis Alpha 通过 MCP 提供结构化数据与规则输出。Hermes 提供推理、解释、记忆与复盘。

正确的职责划分如下：

- Aegis Alpha MCP：数据访问、评分输入、时间戳、提供商状态、以及确定性信号合约。
- Hermes：解读输出、遍历 5 因子、赋予 `promotion_likelihood` 与 `grade`、解释取舍、应用本技能、记住用户偏好、准备复盘笔记。
- 人类用户：最终决策。
- 未来风控引擎：在任何纸上或真实委托工作流之前必备。

## 必需的 MCP 工具

优先使用 Aegis Alpha MCP 工具。Hermes 可能以服务器前缀（如 `mcp_aegis_alpha_`）暴露它们。

核心工具：

- `get_market_sentiment_gate`
- `get_market_emotion`
- `get_theme_leaders`
- `get_theme_continuity`
- `get_top_themes_today`
- `get_limit_up_ladder`
- `get_auction_analysis`
- `get_seal_timeline`
- `get_second_board_candidates_compact`
- `get_second_board_candidates`
- `get_historical_second_board_candidates`
- `get_historical_first_board_watchlist`
- `get_strategy_watchlist`
- `get_daily_strategy_candidate_pool`
- `run_historical_strategy_replay`
- `run_historical_trigger_validation`
- `get_intraday_theme_copump`
- `get_intraday_orderflow_confirmation`
- `sample_realtime_large_trade_proxy`
- `simulate_historical_orderflow_proxy`
- `get_strategy_decision_packet`
- `get_second_board_next_day_outcomes`
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
- `get_promotion_dossier`
- `get_agent_judgment_scorecard`
- `record_selection_audit`
- `get_selection_audit`
- `get_selection_trigger_validation`
- `get_market_sector_breadth`
- `get_sector_breadth_continuity`
- `get_news_alignment`
- `get_tick_rule_orderflow_proxy`

辅助工具：

- `get_market_snapshot`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_orderbook_snapshot`
- `get_stock_history_limitup_stats`
- `review_candidate_outcome`
- `record_candidate_outcome`

`get_market_sentiment_gate` 返回市场**事实**——而非操作标签。字段包括：`limit_up_count`、`break_board_rate`、`hot_theme_count`、`risk_flags`、`positive_signals`、`conclusion`、`yesterday_limitup_today_premium_pct`、`consecutive_boards_alive_rate`、`first_to_second_promotion_rate`、`second_to_third_promotion_rate`、`max_height_today`。不要将其当作闸门指令；**agent** 读取事实并自行做出环境判断。

`get_historical_first_board_watchlist(as_of_day)` 仅返回在该历史收盘时应当可知的事实，用于严格的回放问题，如"站在 2026-06-16 收盘，选出明日最值得观察的二板 Top3"。在做出 Top3 判断之前使用此工具。在明确划分事后验证步骤之前，不要调用目标日的二板工具。

`get_daily_strategy_candidate_pool(as_of_day, limit)` 是用户最终工作流的首选第一步：收盘事实 → agent 选择观察 TopN → 目标日触发事实。它从首板和大量换手趋势种子中返回纯事实的每日候选池，包含 10 日成交额、T-1/as-of-day 缩量、前高突破事实、市场内题材持续性、来源计数、覆盖度和显式数据缺口。它**不**按 alpha、评分、概率或等级排序。提供商顺序不是 agent 排序。

`get_strategy_watchlist(as_of_day)` 是用户广义趋势策略的低层级严格回放入口。返回 `{result_count, candidates, data_gaps}`，候选来自首板和大量换手趋势种子的合并，暴露 10 日成交额基线、T-1/as-of-day 缩量、前高突破、候选来源、以及局部同题材宽度。它同样不返回程序评分、概率或等级。除非需要旧版紧凑结构，否则优先使用 `get_daily_strategy_candidate_pool` 进行每日 TopN 选择。不要将 MA5 斜率当作用户当前策略的一部分；该规则已暂时移除。

`get_theme_continuity(theme, as_of_day, lookback_days)` 返回一个题材的市场内两周持续性事实：活跃天数、爆发天数、总涨停数、日最高涨停数、近期涨停数、以及描述性标签（如 weak/emerging/persistent/fading）。它**不**检查盘外新闻或财联社弹窗，也**不是**买卖评分。

`run_historical_strategy_replay(as_of_day, target_day, symbols, limit, window_start, window_end)` 在历史分钟 K 线上回放用户的盘中形态，针对 as-of 策略观察列表：开盘窗口突破前高、回踩缩量、重新上冲告警。当用户要求站在 9-10 点时段时，使用 `window_start="09:31", window_end="10:00"`。它仅返回研究告警事实。每条结果包含 `pattern_diagnostics`，含前高突破事实、开盘窗口突破事实、量能确认突破状态、以及 `no_signal_reason`；用这些来解释某只股票为何未触发。它不包含未来结果标签，也不检查历史 Level-2 大单占比、财联社弹窗或盘外新闻。监控窗口默认值已固化在 config/runner.yaml 与 runner DEFAULT_MONITOR_WINDOWS: open_drive 09:30–09:50、late_morning 11:10–11:30（策略第6点）。replay/live 工具未显式传 window_start/window_end 时，应使用这两个窗口。

`run_historical_trigger_validation(end_day, lookback_days, limit, window_start, window_end)` 在近期交易日内运行紧凑的历史验证表。对每个目标日，它使用前一个交易日的策略观察列表，回放指定盘中窗口，统计触发/未触发原因，并附加触发后结果标签。将触发后标签仅视为校准参考；绝不可将其当作 as-of 决策输入。

在验证输出中，`intraday_theme_copump` 是用户"同板块一起拉升"条件的最接近当前代理。它统计策略观察列表样本中在该信号时间之前已突破前高或触发的同题材股票数量。将其用作辅助共拉事实，但需明确说明这不是全市场实时板块宽度。

`get_intraday_theme_copump(symbol, as_of_day, target_day, trigger_time, window_start, window_end, peer_limit)` 从完整策略观察列表（而非仅显示的验证样本）中检查同题材 peer。当用户询问某个触发是否有板块/题材共拉时使用。它仍是代理：直接从当前 jvQuant 语义查询获取的全市场行业成分宽度不可靠。

`get_intraday_orderflow_confirmation(symbol, trading_day, trigger_time, window_start, window_end)` 检查在回放/实时触发附近是否有资金流确认可用。当前 jvQuant 历史接线**不**提供经过验证的分钟级主动大单买入占比；该工具暴露为 `historical_big_order_buy_ratio_available=false`，可能仅返回一个弱的日级资金流代理（`主力净额` / `超大单净额` / `大单净额` 除以日成交额）。它还暴露 `realtime_orderflow_capability`：当前 `lv2` 可支持无方向的大单金额代理，但 `active_trade_side_available=false`，因此 `can_compute_big_order_buy_ratio=false`。不要将此代理转换为触发窗口的买入占比声明。用它来明确命名缺失的盘口资金条件，并在日级资金流可用时提供弱语境。

`sample_realtime_large_trade_proxy(symbol, duration_seconds, threshold_cny, window_start, window_end)` 打开一个短时只读 lv2 采样，返回 `directionless_large_trade_amount_cny` 统计：交易笔数、总金额、最大单笔金额、以及高于阈值的近期采样交易。这仅是一个弱盘口活跃度代理。它**不能**区分主动买入与主动卖出，绝不能被描述为 `big_order_buy_ratio`。若 `sample_available=false` 或 `raw_message_count=0`，说明实时提供商在采样期间未发送 lv2 消息；不要将零笔数解读为真实无大单。

`simulate_historical_orderflow_proxy(symbol, trading_day, window_start, window_end, volume_ratio_threshold)` 从历史分钟 K 线模拟弱盘口活跃度。它标记相对于开盘基线的量能放大分钟。这在用户要求在非交易时段进行模拟时有用，但它**不是**历史 Level-2，**不是**逐笔大单，也**不是**主动买卖方向。

`get_strategy_decision_packet(as_of_day, target_day, symbols, limit, window_start, window_end, include_minute_volume_proxy, include_full_theme_copump)` 是用户需要完整策略式回答时的首选端到端事实包。它将 as-of 策略事实、target-day 回放、包内同题材共拉、以及资金流可用性/代理事实打包在一起，减少工具调用漂移。它**不**赋予评分或等级；Hermes 仍须做出 Top3/grade/promotion_likelihood 判断。默认保持 `include_minute_volume_proxy=false`，除非用户显式要求离线模拟。默认保持 `include_full_theme_copump=false`；仅在用户要求更广泛的同题材回放时才开启，因为速度较慢。

`get_historical_second_board_candidates(trading_day)` 和 `get_second_board_next_day_outcomes(trading_day, symbols)` 返回历史**事实**和客观的 T+1 标签。它们不返回程序评分、概率或等级。当用户询问该方法是否可用、要求回放/回测式证据、询问某判断为何失败、或在信任实时候选之前要求历史对比时，使用它们。这些是针对已知交易日的事后工具；它们不可作为 as-of-close 回放的首发候选池。

`get_market_sector_breadth(trading_day, theme)` 与 `get_sector_breadth_continuity(theme, as_of_day, lookback_days)` 提供全市场板块宽度事实（同花顺 THS 概念体系，成分股×当日涨停池 join），升级了原先只看候选池的 packet-local 同题材代理。输出带 `concept_system="ths"` 与覆盖度；数据源（AkShare）不可用时返回 `data_mode="unavailable"`，不得脑补。THS 体系与东财体系归类存在差异，这是市场内板块事实，非交易所官方归类。

`get_news_alignment(symbol_or_theme, lookback_days)` 提供合规新闻/公告对齐事实（巨潮资讯公告）。这是合规替代，**明确不是财联社电报原文**（`source_is_caixin=false`）；只作题材持续性的弱证据辅助，不作主信号。取数失败时降级，不得伪造消息面。

`get_tick_rule_orderflow_proxy(symbol, window_start, window_end, big_trade_threshold_cny, limit_up_price)` 用 tick-rule 从 lv2 逐笔价格序列推断大单主动买入占比。**这是推断代理，非交易所真值 BS flag**（`is_exchange_truth=false`、`method="tick_rule"`）；A股实测精度约70-80%，且封板博弈时系统性虚高——当 `sealing_distortion_warning=true`（价格触及/接近涨停）时该占比不可信，不得当作主动买入真值。它是买点的资金确认弱证据层，买点主链（过前高→回踩缩量→重新上冲）不依赖此值。与 `sample_realtime_large_trade_proxy`（无方向金额）互补。

若这些工具不可用，首先要求 Hermes 用 `/reload-mcp` 重载 MCP，或检查 Hermes MCP 配置。不得伪造实时数据。

## 数据可用性与时效性

若 Aegis Alpha MCP 超时、返回错误或提供空数据，显式声明 `数据源不可用` 并中止候选分析。不得猜测、插值或回填缺失的速度、盘口、大单或题材指标。

在交易时段进行评级前，验证速度、大单和盘口数据的时间戳。交易时段为 09:30-11:30 和 13:00-15:00 Asia/Shanghai。若任何必需的实时字段延迟超过 3 分钟，将最高评级限制为 `B`，将 `promotion_likelihood` 限制为不得为 `high`（只能为 `medium` 或 `low`），警告用户，且不要将候选描述为高置信度。若 `five_min_speed_window` 以 `provider_exact_window:` 开头，报告该确切的提供商窗口；若为 `provider_latest_rolling_5m`，说明提供商未暴露确切的五分钟起止时间。

若 `five_min_speed_window` 以 `minute_replay_exact_window:` 或 `minute_replay_partial_window:` 开头，说明 Aegis Alpha 从 jvQuant 分钟回放 K 线重新计算了速度。分钟回放是分钟级回放数据，不是逐笔实时 Level-2。在交易时段，使用 `five_min_speed_timestamp` 或 `minute_replay_timestamp` 在评级前检查时效性。

对于事件驱动的复盘，消费 `MarketEvent` 和 `SignalSnapshot` 输出。不要索要原始 WebSocket 消息，不要从单个 tick 推断。若事件的 `freshness_status` 为陈旧或未知，将其解释为低置信度语境而非实时触发器。

当用户询问实时监控是否活跃时，使用 `get_runner_status`。若 runner 状态不是 `RUNNING`，不要将 Aegis Alpha 描述为正在活跃监控市场。

## 标准工作流

1. 在分析个别候选之前检查市场情绪闸门。调用 `get_market_sentiment_gate` 并读取其返回的**事实**：`limit_up_count`、`break_board_rate`、`hot_theme_count`、`risk_flags`、`positive_signals`、`conclusion`、`yesterday_limitup_today_premium_pct`、`consecutive_boards_alive_rate`、`first_to_second_promotion_rate`、`second_to_third_promotion_rate`、`max_height_today`。若这些情绪字段全为零并附有说明其为占位符，将其视为不可用而非冷市信号。

2. 从市场事实中做出你自己的环境判断：
   - 高 `break_board_rate`（如 > 30%）和/或低 `limit_up_count` 和/或窄 `hot_theme_count` → 环境不利；解释原因，保持防守，不追逐打板候选。
   - 中等风险标志加一些积极信号 → 谨慎选择性立场；强调需要改善的地方。
   - 低 `break_board_rate`、健康的 `limit_up_count`、广泛的 `hot_theme_count`、积极的 `first_to_second_promotion_rate` 或 `consecutive_boards_alive_rate` → 环境支持选择性打板。

3. 若 Aegis Alpha 数据不可用、陈旧超过时效规则、或为空，在继续之前遵循数据可用性规则。

4. 若市场事实支持打板（可控的炸板率、足够的涨停宽度、至少一个活跃热门题材），调用 `get_theme_leaders` 和 `get_market_emotion` 获取板块级别语境，然后用 `get_second_board_candidates_compact` 获取二板候选。当你需要确认单只股票的连板高度时使用 `get_limit_up_ladder(symbol)`；候选输出已携带 `previous_consecutive_boards`、`previous_height_label`、`theme_role` 和 `theme_leader_symbol`，因此通常不需要对每只候选额外调用。

5. 若 Aegis Alpha 返回近期市场事件，将其用作重新评分的语境，但不要将事件建议视为委托指令。

6. **优先使用 `get_promotion_dossier(symbol)` 一次获取全部五个因子**——它返回 `market_emotion / theme_position / float_size / volume_energy / reseal_strength` 作为纯事实打包（无评分），这样你就不会意外跳过任何因子。仅在 dossier 不可用时才回退到单独工具。

   对**每只**候选，你**必须**显式遍历全部 5 个因子。不得只给综合总结——不得只给综合总结而跳过任一因子的逐项说明。必需的 5 个因子为：

   **因子 1 — 市场情绪（market_emotion）**：从市场闸门事实衍生：`break_board_rate`、`limit_up_count`、`yesterday_limitup_today_premium_pct`、`first_to_second_promotion_rate`、`consecutive_boards_alive_rate`、`hot_theme_count`。用一句中文说明市场环境对该候选成功概率意味着什么。示例："涨停42家，炸板率18%，连板存活率62%，市场情绪较好，对二板进攻有支撑。"

   **因子 2 — 题材所在位置（theme_position）**：从候选中读取 `theme_lifecycle_stage`。生命周期阶段为：`launch`（启动）→ `fermenting`（发酵）→ `climax`（高潮）→ `divergence`（分歧）→ `ebb`（退潮）。**关键规则**：若 `theme_lifecycle_stage` 为 `divergence` 或 `ebb`，你**必须**降权该候选，即使近期热度或涨停率表面看起来很强。这是因为晚期题材携带高反转风险——电力题材高位分歧仍强推二板的失败模式是本规则旨在捕捉的已知失败模式。使用 `theme_role`、`theme_leader_symbol` 和 `get_top_themes_today` 进行佐证。

   具体降权后果（不得例外，即使其他因子都强）：
   - `theme_lifecycle_stage=divergence` → grade 最高只能给 B，promotion_likelihood 最高只能 medium。
   - `theme_lifecycle_stage=ebb` → grade 必须 REJECT，promotion_likelihood 必须 low。
   - `theme_lifecycle_stage=climax`（高潮）：promotion_likelihood 最高只能 medium，除非量能与回封力度同时很强，才可给 high。climax 阶段是分歧前的最后一档，高潮期兑现风险高，必须在因子说明里点出。

   **因子 3 — 股本大小（float_size）**：使用 `free_float_market_cap_cny`。大流通盘降低持续封板概率；小流通盘配合强题材为有利。用一句中文说明流通市值及其影响。

   **因子 4 — 量能与资金（volume_energy）**：使用 `avg_turnover_10d_cny`（10 日均成交额基线）、`prev_day_volume_shrink_ratio`（T-1/as-of-day 是否相对前期基线缩量）、以及 `broke_previous_high`（价格是否突破前期波段高点）。**同时**涵盖 `big_order_net_inflow_ratio`（大单净流入占成交额比例——正值为机构吸筹，负值为派发）和 `orderbook_quality_score`（排队深度和构成质量）。A 级要求大单正流入**且**盘口质量强劲；若任一缺失或为负，将评估限制在 B。用一至两句中文说明整体量能资金图景。注意：JSON 输出字段键名**必须**保持 `volume_energy`（校验器检查该确切键名）。

   **因子 5 — 回封力度（reseal_strength）**：使用 `break_board_count`、`reseal_count`、`max_seal_amount_cny`、`final_seal_time` 和 `seal_to_turnover_ratio`。高 `break_board_count` 配合快速、大额 `reseal_count` 和强劲 `max_seal_amount_cny` 暗示真正的机构护板意图。`final_seal_time` 接近收盘配合高 `seal_to_turnover_ratio` 是积极信号。用一句中文说明回封模式。

7. 遍历全部 5 个因子后，赋予 `promotion_likelihood` 和 `grade`：
   - `promotion_likelihood`：**必须**精确为 `high` / `medium` / `low` 三者之一。这代表该候选晋级三板的分档概率。程序校验此字段——不要使用小数、百分比或任何其他格式。
   - `grade`：你作为分析师的判断——精确为 `A`、`B`、`C` 或 `REJECT` 之一。这不由程序产生；agent 基于全貌赋予。
   - 一般对应关系：A→high、B→medium、C/REJECT→low。若 grade 与 promotion_likelihood 出现反差（如 grade=A 但 promotion_likelihood=low），必须在评级原因里明确解释反差原因，不得无声矛盾。

8. 生成观察列表报告。对每只候选，agent 赋予评级并解释原因。始终包含结构化的触发条件和禁止条件。

9. 始终同时声明模型身份和市场数据身份。将 `llm_provider` / `llm_model` 与 `market_data_mode` / `market_data_provider` 分开。

10. 在每只候选之后，用自然中文从 5 因子综合解释推理过程。不要依赖任何程序发出的 `grade_reason` 字段——程序已不再生成该字段。始终从返回的指标自行推导原因。

11. 仅在紧凑输出不充分时才使用完整版 `get_second_board_candidates`。若需要证据详情，优先使用 `get_second_board_candidate_data_quality(symbol)` 而非重新拉取完整候选池，以避免工具输出截断。

12. 对于多时段监控，在会话早期用 `create_watchlist(owner=user, label=YYYY-MM-DD label, symbols=A|B|C)` 创建观察列表。每当候选在盘中评级变化时，用 `update_watchlist_state(watchlist_id, symbol, new_grade, action, note)`。会话结束时用 `close_watchlist(watchlist_id, note)` 封存审计轨迹。用 `list_active_watchlists(owner)` 列出现有观察列表。

13. 用户每次开启新对话时，读取 `get_pending_alerts(limit)` 以获取 runner 在离线期间检测到的内容。对告警采取行动后调用 `acknowledge_alert(alert_id, note)`。runner 持久化 `SEAL_ORDER_DECAY`、`BIG_ORDER_INFLOW_SPIKE` 和 `THEME_DIVERGENCE` 事件的告警；若告警仍为待处理状态，不要重新运行相同分析。

14. 15:10 之后，运行 `generate_daily_review(trading_day=today)` 生成 Phase 3 复盘-修正使用的结构化复盘条目。对于周度模式审计，使用 `generate_weekly_pattern_report(start_day, end_day)`（建议最多 14 天窗口）。

15. 使用 `get_top_themes_today(trading_day, limit)` 获取按成分股数量和龙头连板高度排名的领先题材，当候选的 `theme_role` 显示为 `co_leader` 或 `follower` 时，使用 `get_seal_timeline(symbol)` 检查盘中封板/炸板事件。

16. 收集至少 5 个交易日的结果后，对失败候选运行 `attribute_outcome(symbol, trading_day)` 以识别重复出现的失败模式。在累积 3+ 个相似标签后，将近期归因中的 top primary_tag 作为 Hermes 记忆候选。

17. 当可用时，使用 `get_history_stats(symbol)` 而非依赖占位符式的 `three_year_*` 字段。若 `confidence` 为 `insufficient_sample`，将历史信号视为不可用，不要叙述概率。

18. 当用户询问"收紧规则 X 是否改善命中率？"时，调用 `run_backtest(rule_changes_json, start_day, end_day)` 并报告 `sealed_rate` 差值和 advice。绝不要自动应用阈值提议——它们始终需要 `record_correction_action_decision` 定义的人工确认流程。注意：阈值回测工具目前正在重新安置（Phase 7），对某些规则变更类型返回 unavailable；在重新启用之前不要依赖它。

19. P5 数据维度可选用：
    - `get_dragon_tiger(symbol, trading_day)` 在收盘后查看候选股的龙虎榜结构；如席位含 `hot_money_known` 且 `hot_money_alias` 为白名单游资（章盟主、孙哥等），在评级原因里点出资金主体。
    - `get_active_seats_today(trading_day)` 看当天哪几位游资同时进入多只股，用作板块共振辅助证据。
    - `get_limit_down_pool(trading_day)` / `get_st_pool(trading_day)` 在判断市场情绪时观察反向池规模；如 `MARKET_BOTTOM_REVERSAL` 事件出现，将其当作板块见底的辅助语境，不要由它直接推荐买点。
    - 候选契约里 `limitup_driver_type` 与 `intraday_pattern` 在 evidence 里给一句中文备注；`policy` / `earnings` 驱动通常比 `theme` 更稳，`one_word_board` / `platform_breakout` 比 `messy_board` / `false_breakout` 风险更低。
    - `get_capital_flow_slices(symbol, trading_day)` 在复盘失败案例时使用：`tail_30m` 主力净流出说明尾盘机构离场。

20. P4 盘中买点离线回放（Phase 4，按需使用）：
    - `detect_intraday_buypoint(symbol, end_day, previous_high)` 返回盘中买点形态的离线回放告警（过前高→回踩缩量→重新上冲）。这是研究告警，不是下单指令。当前为离线历史回放（实盘盘中监控是后续阶段）；阈值用默认值，策略 prior（后续阶段）会让均量 > 50 亿等阈值可切换。把返回的 `signals` 当作观察证据，结合五因子判断，不要据此直接下单。若未传 `previous_high`，工具会用开盘前 3 根 bar 的最高 `last_price` 作为保守替代；传入明确前高更准确。

21. P6 进阶能力（按需使用）：
    - `find_similar_setups(symbol, lookback_days, similarity_threshold)` 在复盘候选时找相似历史样本；当返回的 `similarity ≥ 0.85`，可作为"这个形态历史上确实经常打成功"的弱证据，但不要替代当下行情判断。注意：历史快照的 agent/human 评级（若有记录）为弱参考，若为 None 则完全忽略。
    - `get_new_stock_candidates()` 返回的 `tier_aged_out` 不应再按次新处理；`tier_a_smallcap_recent` 才是典型的次新打板候选。
    - `get_suspended_stocks(trading_day)` 在每次拉候选前检查；候选若出现在停牌列表中应直接 REJECT 并提示数据脏。
    - `query_minute_bars(symbol, start_day, end_day)` 仅在 history-store extras 安装后可用；返回 `data_mode=unavailable` 时直接告诉用户分钟级历史层未启用。
    - `simulate_outcome(symbol, trading_day, hypothesis_json)` 在用户问"如果当时封单是 X 亿，评级会变吗？"时调用；返回 `payload_diff` 是结构化对比，不是确定性结论。P8 起它会用真 `candidate_grade()` 重算：你可以传任意 `{"action": "avoid"}` / `{"orderbook_quality_score": 80.0}` 等覆盖来观察 `hypothetical_grade` 变化。
    - 候选契约里的 `weekly_health_score` ≥ 70 表示周线位置健康，可加分；< 30 应在评级原因里点出周线劣势。
    - 板块事件 `THEME_LEADER_BREAK_BOARD`（高度龙头炸板）与 `SECTOR_ROTATION`（板块轮动）：当 `get_recent_market_events` 返回这两类事件时，把它们当作板块级风险/机会语境而不是单股触发——前者意味着同题材 follower 应整体降级，后者意味着可以把注意力从 weakening_theme 转向 strengthening_theme 的 followers。P8 起，板块事件 `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION` / `MARKET_BOTTOM_REVERSAL` 会触发 runner macOS 告警；通过 `get_pending_alerts(limit)` 拉到的告警里会带这 3 类。
    - 停牌过滤已在 P7 自动接入候选拉取链路——候选列表中不会再出现停牌股；如人工手动评估某只票，仍可调 `get_suspended_stocks(trading_day)` 复核。
    - `simulate_outcome` 的 `hypothetical_grade` 现在来自完整 candidate_grade 重算，不再受限于 P7 的 `seal_amount_cny` / `five_min_speed_pct` 两字段启发。

22. 历史 replay / 可用性验证（按需使用）：
    - 严格 as-of replay：当用户说"站在 YYYY-MM-DD 收盘，选明日最值得观察的二板 Top3"或"生成明日观察池"时，优先调用 `get_daily_strategy_candidate_pool(as_of_day=YYYY-MM-DD)`。如果该工具不可用，才退回 `get_strategy_watchlist(as_of_day=YYYY-MM-DD)`；再不可用才退回 `get_historical_first_board_watchlist(as_of_day=YYYY-MM-DD)`，并明确说明策略字段不足。在给出 Top3 之前，不要调用 `get_historical_second_board_candidates(target_day)`，不要读取 `target_day` 的涨跌幅、封板结果或 T+1 outcome。
    - 严格 as-of replay 的初始 Top3 阶段只使用 `get_daily_strategy_candidate_pool` / `get_strategy_watchlist` / `get_historical_first_board_watchlist` 返回的事实池。跳过标准实时工作流里的 `get_market_sentiment_gate`、`get_active_strategy_prior`、`get_theme_leaders`、`get_promotion_dossier`、实时盘口/分钟回放等工具，除非用户在 Top3 之后明确要求补充验证。
    - 对每只入选标的，必须逐条说明：近10日均成交额是否大于50亿、T-1/as-of-day是否缩量、T日是否突破前高、板块持续性数据是否充分、候选来自 `first_board_watchlist` 还是 `large_turnover_trend_seed`。`theme_continuity.continuity_label` 只能作为市场内板块持续性事实；盘外新闻/财联社若未接入，必须列为缺口，不得脑补。当前策略暂不使用"5日均线斜率30°到60°"。
    - 当用户问"这个方向能不能验证""为什么 agent 这么判断""今天二板环境与历史相似吗"时，先调用 `get_historical_second_board_candidates(trading_day)` 取历史候选事实，再调用 `get_second_board_next_day_outcomes(trading_day, symbols)` 取 T+1 结果。
    - 你的任务是用历史事实校准自己的判断，不要要求程序提供评分权重。程序只给数据；agent 给 `promotion_likelihood` 和 `grade`。
    - 对比至少三个朴素基准：封单额优先、封成比/封成比近似优先、首次封板时间优先。先列出这三个基准 Top3，再给你的 agent Top3。
    - 反机械排序规则：如果你的 Top3 与任一朴素基准 Top3 完全相同，必须重新评估。若重新评估后仍保持一致，必须明说"当前判断主要等同于某某基准排序，尚未体现额外 alpha"，并把整体置信度降到 exploratory/low-confidence。
    - 入选解释必须是相对解释：每只入选标的至少说明一个"它胜过某只高封单额/高封成比/更早封板但落选标的"的理由。如果说不出相对优势，不要把它列为 A。
    - 封成比/封单额只能作为封板质量证据，不得作为唯一或主排序理由。在 strict as-of replay 的 Top3 生成阶段，不要引用同一 replay 的未来失败/成功案例；这些只能在明确标注为 post-hoc validation 的段落里使用。
    - 输出历史 replay 结论时，区分"胜过候选池平均"和"胜过简单基准"。前者只能说明有基础筛选价值；后者才说明 agent 判断可能有额外价值。
    - 不要从单日 replay 推断稳定胜率。若样本少于 10 个交易日，结论必须标为 exploratory。
    - 盘中历史 replay：当用户要求"用已发生数据模拟当时事实"或"模拟买点触发"时，优先调用 `get_strategy_decision_packet(as_of_day, target_day, symbols, limit, window_start, window_end, include_minute_volume_proxy=false, include_full_theme_copump=false)`，除非用户只要求单只票的原始 replay。输出必须分清：收盘观察池事实、target_day 分钟级触发事实、packet-local 同题材共振事实、缺失数据（历史大单买入占比/财联社/盘外新闻）、以及是否出现 research alert。不要把 research alert 写成买入指令。
    - 历史样本验证：当用户要求"验证可用性""跑一段历史样本""看看触发器命中率/误报"时，调用 `run_historical_trigger_validation(end_day, lookback_days, limit, window_start, window_end)`。必须区分 replay 触发事实和 post-trigger outcome；后者只能用于校准。

## 策略 Prior

每个会话调用一次 `get_active_strategy_prior` 加载活跃策略 prior（当前为 `client_10pt`——客户口述的二板买点策略）。prior 是**指导，而非过滤器**。它携带客户关心的软性理想区间和定性注释。程序绝不根据 prior 接受或拒绝候选；**你**将每只候选的实测事实与 prior 权衡并做出决定。

如何使用：

- **软区间（`thresholds`）**：每个阈值具有 `ideal_low`/`ideal_high`/`unit`/`rationale`。将候选的实测事实与理想区间比较，并在你的因子撰写中报告比较结果。当前此策略的活跃区间：近10日均成交额 ideal ≥ 50亿（`avg_turnover_10d`）。暂时忽略 MA5 斜率，即使较旧的 prior 或候选对象中包含它。
- **带推理的覆盖（强制）**：在 prior 理想区间**之外**的候选**不**自动拒绝。若事实证明合理，保留该候选并显式声明覆盖。同样，处于每个活跃区间**之内**并不保证高评级——5 因子判断仍然主导。绝不要将 prior 区间当作通过/不通过的闸门。
- **指导注释（`guidance_notes`）**：编织进你的推理中的定性项目——板块两周持续性（可能需要你做盘外信息确认）、T-1 缩量、T 日带量过前高、回踩缩量后重新上冲=买入预警点、同板块共振加分、重点监控时段 9:30–9:50 与 11:10–11:30。
- **板块两周持续性**是由 prior **引导**的 agent 任务：当 prior 标记它时，你应寻求盘外佐证（盘外抓取）该板块在过去两周是否展现出反复的多日强势，并说明——若无法确认则不可伪造。
- **财联社消息**：`caixin_alignment` 在本周期为占位符（本期暂不接入财联社消息源）。不要声称存在财联社对齐信号；将其视为尚不可用。

若 `get_active_strategy_prior` 返回 `data_mode: unavailable`，在没有 prior 的情况下按标准 5 因子工作流继续，并注明未加载活跃 prior。

## 候选解读规则

将其用作 agent 评级启发式规则，除非用户记忆或 Aegis Alpha 输出提供了具体指导：

- `A`：市场事实表明支持性环境（低炸板率、充足的涨停宽度、积极的晋级率）；同题材联动强劲；`theme_lifecycle_stage` 为 `launch` 或 `fermenting`（climax 见下方天花板规则）；盘口质量强劲；大单正流入；量能显示扩张；回封力度令人信服；历史统计有利。
- `B`：密切关注，但至少一个重要因子不理想——包括但不限于缩量、混合市场宽度、或高潮阶段题材风险。`theme_lifecycle_stage=divergence` 总是把 grade 限制在 B（即使其他因子都强）。
- `C`：仅观察；不要将其描述为可操作。
- `REJECT`：不在昨日有效涨停池中；市场整体炸板率高且宽度崩溃（agent 从事实判断）；题材龙头炸板；`theme_lifecycle_stage=ebb`（退潮阶段一律 REJECT，不论封单多大）；或数据质量不足。

若速度、大单或盘口时间戳在交易时段延迟超过 3 分钟，最高评级为 `B`，`promotion_likelihood` 不得为 `high`。

对于二板分析，优先选择更少候选、更好解释，而非宽泛列表。

## 输出格式

使用此结构进行面向用户的回答。`factor_analysis` 块和 `promotion_likelihood` 对每只候选都是**强制**的。省略任一因子或以综合总结替代因子遍历是对本技能合约的违反。

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
   - 量能: <说明 avg_turnover_10d_cny / prev_day_volume_shrink_ratio / broke_previous_high / big_order_net_inflow_ratio / orderbook_quality_score>
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

具体禁止条件示例包括：高开低于 3%、竞价抢跑、同题材龙头跌破盘中 VWAP、盘口质量跌破阈值、大单净流入转负、或炸板率快速扩张。

不要写"买入"、"必须买入"、"卖出"、"全仓"或"保证"。使用"观察"、"候选"、"触发条件"、"禁止条件"和"风险"。

## 安全规则

- 绝不索取或暴露券商凭证、交易密码或真实委托令牌。
- 绝不根据本技能提出真实自动交易。
- 绝不将模拟数据当作真实市场数据。
- 绝不忽视市场情绪闸门事实。
- 当市场整体炸板率高或涨停宽度崩溃时绝不推荐打板（agent 从事实判断）。
- 绝不分析任意代码作为二板候选，除非它们在有效的前日涨停池中，或用户显式要求假设性复盘。
- 若数据陈旧、缺失或不一致，降低置信度并说明。
- 策略 prior 仅是指导：绝不将 prior 的区间应用为硬性通过/不通过过滤器，绝不让 prior 覆盖实测事实——事实优先，任何偏离 prior 之处必须附推理说明。

## 复盘与记忆

当用户纠正一个判断时，总结可复用的教训并询问是否记住。
使用 `record_candidate_outcome` 记录显式复盘事实或用户纠正；不要将传闻、凭证或未经验证的提示存储为 outcome。

好的记忆候选：

- 用户更偏好二板结构而非首板结构。
- 用户不喜欢没有题材联动的快板。
- 用户在炸板率高时希望减少活动。
- 用户关心次日开盘和封板二板后的第三日溢价。
- 晚期题材（`divergence`/`ebb`）即使短期热度看起来很强也应降权（电力题材高位失败教训）。

不要将原始股票提示、凭证或一次性市场传闻保存为记忆。

## 判断自检（Scorecard）

使用 `get_agent_judgment_scorecard(start_day, end_day)` 查看你在日期窗口内的**历史**调用与实际结果的匹配程度。它返回客观校准指标——`brier_score`（越低说明 promotion_likelihood 校准越好）、`likelihood_calibration`（按 high/medium/low 分桶：预测 vs 实际封板率）、以及 `grade_hit_rate`（按 grade 的实际封板率）——从你存储的复盘 vs 记录的次日结果计算得出。

这是一面自我校准的镜子，不是程序评分，也不是指令。阅读它以发现系统性偏差——例如，若你的 `high` 分桶的实际封板率远低于 0.8，说明你过度自信，应收紧什么条件才能获得 `high`。当窗口内无评分样本时，`sample_size` 为 0，`brier_score` 为 null；不要对微小样本做过分解读。

## 闭环验证（二期A，#3+#4）

闭环验证（二期A,#3+#4）：收盘 agent 从候选池选完 TopN 后，调 `record_selection_audit(as_of_day, picks_json, rejected_json, candidate_pool_size)` 持久化选股决策——picks_json 每只含 symbol/rank/relative_reason（相对理由：为什么它胜过某只更高封单额/封成比的落选股）/caveats（缺失数据，如盘外新闻未确认）；rejected_json 记录落选 near-miss 及 why_rejected/beat_by。程序自动用当天历史二板事实算三朴素基准 TopN（封单额/封成比/首封时间）并标记 `equals_baseline`：若为 true，说明你的 TopN 等同机械基准、未体现额外 alpha，返回里会带 anti_mechanical_warning，你必须重评或明确说明。`confidence_label` 在累计选股记录 <10 个交易日时强制 exploratory。次日（或任意目标日）调 `get_selection_trigger_validation(as_of_day, target_day, window_start, window_end)` 对照闭环：逐只 pick 给出 09:31-10:00 盘中是否过前高/买点触发（trigger_time）+ 次日封板/开盘涨幅，汇总 trigger_rate；盘中/次日事实任一不可用时该字段 data_mode 标 unavailable，不脑补。runner 在交易日 10:00 后自动对最近一条昨收审计跑一次验证并发 SELECTION_VALIDATION 告警（advisory，只读审计+写告警，绝不下单），通过 get_pending_alerts 拉取。样本不足时所有结论标 exploratory，不得据单日/小样本下稳定胜率结论。

## 定时使用

对于 Hermes cron 作业，提示词必须自包含。一个有用的时间表是：

- 09:20：准备昨日涨停池和市场预检。
- 09:30-10:30：监控二板候选列表。
- 15:10：复盘候选是否触及涨停、封板、炸板、并产生预期后续走势。

Cron 输出应简洁，且除非 MCP 数据源为实时，不得声称实时监控。
