# jvQuant Capability Matrix

This matrix is generated from configured read-only jvQuant semantic-query probes.

## Acceptance Rules

- `official_doc`: 来自 jvQuant 官方文档或官网明确说明，可作为优先口径。
- `observed_probe`: 来自本项目只读探针的实际返回字段，只代表当前账号、当前市场、当前时间点观测到的能力。
- `internal_inference`: Aegis Alpha 根据已有字段自行计算的派生指标，必须在输出中说明限制。
- 所有 `_pct` 字段已经是百分比数值，`0.0929` 表示 `0.0929%`，不是 `9.29%`。
- 所有 `_ratio` 字段是比例，`0.0311` 表示 `3.11%`。
- 所有 `_score` 字段默认是 0-100 内部评分。
- 盘中 Agent 只能消费结构化 `SignalSnapshot` / `MarketEvent`，不能直接消费原始 WebSocket payload。
- 缺字段、超时、空数据时必须返回 `Data source unavailable` 或降低评级，不能猜测主动买卖方向、排单位置、真实封单队列。

## Realtime WebSocket Observations

| Feed | Probe | Status | Authority | Observed Shape | Current Use | Limitation |
|---|---|---:|---|---|---|---|
| `lv1` | `probe_jvquant_websocket_payload.py --levels lv1` | pending_more_samples | observed_probe | 待盘中多标的采样 | 最新价、涨跌幅、成交额进入本地窗口 | 未完成验收 |
| `lv2` | `probe_jvquant_websocket_payload.py --levels lv2` | observed | observed_probe | 最新成交样本字段数为 4；2026-06-18 盘后对 `002281` 复核仍为 `time/trade_id/price/volume` | 大额成交金额粗筛 | 当前样本未观察到主动买卖方向，不能计算主动大单买入占比 |
| `lv10` | `probe_jvquant_websocket_payload.py --levels lv10` | pending_more_samples | observed_probe | 历史单元测试覆盖 46 字段形状；需盘中复核 | 十档买卖量、盘口质量、封单估算 | 排单位置和真实队列需要更权威字段确认 |

## Derived Realtime Signals

| Signal | Source | Authority | Implementation | Notes |
|---|---|---|---|---|
| `speed_1m_pct / speed_3m_pct / speed_5m_pct / speed_10m_pct` | `lv1/lv10` price windows | internal_inference | `SignalWindowBuffer.speed_pct` | 由本地窗口计算，依赖 runner 持续采样。 |
| `big_order_net_inflow_cny` | `lv2` deals | internal_inference | `JvQuantRealtimeClient._on_ab_lv2` | 目前只能按大额成交金额累计，未确认主动买卖方向，因此不是严格“净流入”。 |
| `orderbook_quality_score` | `lv10` depth | internal_inference | `signals/orderbook.py` | 用十档买卖量比例和一档支撑估算。 |
| `ask_pressure_score` | `lv10` depth | internal_inference | `signals/orderbook.py` | 由盘口质量反向叠加封单衰减估算，用于提示卖压。 |
| `sell_wall_amount_cny` | `lv10` depth | internal_inference | `signals/orderbook.py` | 用卖一量乘价格估算上方卖墙金额。 |
| `seal_amount_cny` | `lv10` depth | internal_inference | `signals/orderbook.py` | 当涨幅接近涨停时，用买一量乘价格估算封单额；不是交易所权威封单队列。 |
| `seal_decay_pct` | `lv10` depth over time | internal_inference | `signals/orderbook.py` | 用前后两次估算封单额计算衰减。 |

## Live-Probe Extension Wiring (2026-06-01)

| Capability | Probe | Status | Authority | Current Use | Limitation |
|---|---|---:|---|---|---|
| `weekly_position` | `client.kline(..., type="week")` + day K-line | wired | observed_probe | `get_weekly_position` derives 8-week position and MA20/MA60 from K-line bars | Derived metric; not a vendor-provided health score |
| `limit_down_pool` | `今日跌停,股票代码,股票简称,涨跌幅,连续跌停天数,价格,成交额,行业` | wired | observed_probe | `get_limit_down_pool` returns `ContrarianPoolEntry` rows | Field names remain semantic-query observations |
| `st_pool` | `是否ST=是,股票代码,股票简称,涨跌幅,价格,成交额,行业` | wired | observed_probe | `get_st_pool` returns ST `ContrarianPoolEntry` rows | Some provider rows expose `-` price/amount values |
| `new_stock_candidates` | `上市天数小于180,...` | wired | observed_probe | `get_new_stock_candidates` parses listing date/days/free-float market cap | Uses semantic-query free-float market-cap string parsing |
| `suspended_stocks` | `今日停牌,...` / `停牌中,...` / `停牌状态=停牌,...` | wired_confirmed_empty | observed_probe | `get_suspended_stocks` parses rows and treats empty provider result as confirmed-empty | Probe day count was 0; parser covered by field-compatible fixture |
| `dragon_tiger_raw` | `今日龙虎榜,股票代码,股票简称,上榜原因,买入金额,卖出金额,净买入额` | wired_raw | observed_probe | `get_dragon_tiger` flattens nested `龙虎榜YYYY-MM-DD` records | Stable individual营业部 names were not observed |
| `daily_capital_flow` | `symbol,股票代码,股票简称,主力净额,超大单净额,大单净额,中单净额,小单净额,...` | wired_scope_reduced | observed_probe | `get_capital_flow_slices` returns one `"daily"` slice | Not minute-level Level2 主力/散户 decomposition |
| `active_seats_today` | `今日龙虎榜,营业部名称,...` | placeholder | observed_probe | Placeholder signal remains | Raw龙虎榜 exists, but stable seat alias aggregation is not confirmed |

| Capability | Probe | Status | Authority | Count | Observed Fields | Notes |
|---|---|---:|---|---:|---|---|
| second_board_speed_and_capital_flow | second_board_speed_capital | available | observed_probe | 12 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `区间涨跌幅(1分钟)@2026-05-27 14:55:00-2026-05-27 15:00:00`, `主力净额2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_short_interval_speed | second_board_speed_1m | available | observed_probe | 12 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `区间涨跌幅(1分钟)@2026-05-27 14:59:00-2026-05-27 15:00:00`, `收盘价(日线不复权)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_short_interval_speed | second_board_speed_3m | available | observed_probe | 12 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `区间涨跌幅(1分钟)@2026-05-27 14:57:00-2026-05-27 15:00:00`, `收盘价(日线不复权)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_short_interval_speed | second_board_speed_10m | available | observed_probe | 12 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `区间涨跌幅(1分钟)@2026-05-27 14:50:00-2026-05-27 15:00:00`, `收盘价(日线不复权)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_seal_metrics | second_board_seal_metrics | available | observed_probe | 8 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `涨停首次封板时间2026-05-27`, `涨停封单额2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_max_seal_metrics | second_board_max_seal | available | observed_probe | 10 | `代码`, `名称`, `涨跌幅2026-05-27`, `涨停封单量(股)2026-05-27`, `涨停封单额2026-05-27`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `收盘价(日线不复权)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| second_board_break_and_reseal | second_board_break_reseal | available | observed_probe | 2 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `涨停最终封板时间2026-05-27`, `炸板次数(次)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| today_limitup_seal_metrics | today_limitup_seal_metrics | available | observed_probe | 47 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停2026-05-27`, `涨停首次封板时间2026-05-27`, `涨停封单量(股)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| multi_board_seal_metrics | multi_board_seal_metrics | available | observed_probe | 8 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `连板(天)2026-05-27`, `涨停首次封板时间2026-05-27`, `涨停封单量(股)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| break_board_pool | break_board_pool | available | observed_probe | 34 | `代码`, `名称`, `涨跌幅2026-05-27`, `行业分类二级`, `是否ST2026-05-27`, `炸板次数(次)2026-05-27`, `涨停回封次数(次)2026-05-27`, `收盘价(日线不复权)2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| auction_metrics | auction_metrics | available | observed_probe | 46 | `代码`, `名称`, `行业分类二级`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `集合竞价涨跌幅2026-05-27`, `集合竞价成交额2026-05-27`, `集合竞价换手率2026-05-27`, ... | Observed by probe; not a contractual field definition. |
| theme_and_concept | theme_concept_metrics | available | observed_probe | 11 | `代码`, `名称`, `涨跌幅2026-05-27`, `成交额2026-05-27`, `是否ST2026-05-27`, `是否涨停@2026-05-26`, `概念`, `个股题材`, ... | Observed by probe; not a contractual field definition. |
| historical_limitup_followthrough | historical_limitup_followthrough | fields_observed_empty_result | observed_probe | 0 | `名称`, `代码`, `行业分类二级`, `涨停次数(次)@2023-05-29-2026-05-27`, `近十个交易日【2026.05.14-2026.05.27】涨停 后 次日【2026.05.14-2026.05.27】高开`, `是否涨停2026-05-27` | Observed by probe; not a contractual field definition. |
