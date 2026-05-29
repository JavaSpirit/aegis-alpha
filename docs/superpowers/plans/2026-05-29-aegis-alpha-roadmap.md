# Aegis Alpha 终极版本路线图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement individual phase plans linked below. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Aegis Alpha 从「读 jvQuant 语义查询的二板雷达 MVP」演进为「闭环可学习的打板研究系统」——评级有龙头/连板/情绪基础，盯盘有持续工作流，纠错有反馈回路，运营有日志/限流/指标。

**Architecture:** 分 7 个阶段，每阶段产出独立可用的能力，无大爆炸式重构。前两阶段（P0+P1）解决正确性 bug 和评级阈值外置，是后续 ML / backtest / 反馈闭环的前置条件。每阶段一份独立 plan 文档，本路线图只做导航和依赖关系记录。

**Tech Stack:** Python 3.11+, Pydantic v2, FastMCP, SQLite (+ schema migrations), pytest, jvQuant SDK, PyYAML, threading.Lock, optionally pyarrow/duckdb 后续。

---

## 阶段总览

| 阶段 | 主题 | 预估周期 | 前置依赖 | Plan 文档 |
|------|------|---------|---------|-----------|
| **P0** | 正确性修复（speed_pct 语义、涨停板上限、线程安全、时间格式） | 1 周 | 无 | `2026-05-29-p0-correctness-fixes.md` ✅ |
| **P1** | 架构基础（Adapter Protocol、jvquant 拆分、评级阈值外置、统一时钟、单例 store/adapter、超时与限流、日志、迁移） | 2 周 | P0 | `2026-05-29-p1-architecture-foundations.md` ✅ |
| **P2** | 评级核心数据补全（板块龙头、连板高度、情绪温度计、竞价分析） | 2 周 | P1 | `2026-05-29-p2-grading-core-signals.md` ✅ |
| **P3** | 持续工作流（盯盘列表、分歧→一致追踪、复盘报告、告警） | 2 周 | P1, P2 | `2026-05-29-p3-watchlist-workflows.md`（待展开） |
| **P4** | 反馈闭环（失败案例库、历史回测框架、纠错→评级阈值自动建议） | 3 周 | P1, P2, P3 | `2026-05-29-p4-feedback-loop.md`（待展开） |
| **P5** | 数据维度扩展（龙虎榜、跌停池、涨停原因细分、分时形态识别） | 3 周 | P1, P2 | `2026-05-29-p5-data-extensions.md`（待展开） |
| **P6** | 进阶事件与生态（板块事件、跨周期校验、相似形态搜索、Parquet 历史层） | 3 周 | P2, P3, P4 | `2026-05-29-p6-advanced-events.md`（待展开） |

✅ = 本次同时产出的详细 plan
（待展开）= 本路线图给出 scope/任务列表，需求确认后再写步级 plan

**MVP 关键路径：** P0 → P1 → P2 → P3 即可拿到「评级可信 + 工作流闭环 + 复盘可用」的产品。P4-P6 是把它从可用提升到优秀的强化阶段。

---

## 依赖图

```text
P0 (正确性) ─┬─→ P1 (架构) ─┬─→ P2 (评级数据) ─┬─→ P3 (工作流) ─┬─→ P4 (反馈闭环)
              │                │                  │                │
              │                └─→ P5 (数据扩展) ─┴────────────────┴─→ P6 (生态)
              │
              └─→ 任何路径都先经过 P0
```

P0 必须最先做：speed_pct 语义错误会污染所有评级数据，先放着做 P2 等于在错的地基上盖楼。
P1 紧随其后：评级阈值不外置，P4 反馈闭环就只能「建议改代码」无法「自动调阈值」。
P2 和 P5 在 P1 之后可以并行（不同适配器/不同表）。
P3 依赖 P2（盯盘列表展示需要龙头/连板信息）。
P4 依赖 P3（反馈需要 outcomes 表的真实数据，P3 才会接入）。

---

## P0 — 正确性修复（详细 plan 见 p0-correctness-fixes.md）

修 4 个直接影响评级正确性的 bug：

1. **`SignalWindowBuffer.speed_pct` 按点数算而非按分钟** — 实盘路径下 `speed_5m_pct` 实际只是「最近 5 个 tick」，可能仅十几秒窗口。改为按 timestamp 二分查找。
2. **`change_pct = 10.0` 推断不区分板种** — 科创板/创业板涨停 20%、北交所 30%。按代码前缀分流。
3. **`SignalWindowBuffer` 非线程安全** — WebSocket 回调在独立线程里 read-modify-write 多个 dict，加 `threading.Lock`。
4. **`first_limit_up_time` 字符串字典序比较脆弱** — `"9:45" > "09:45:00"` 会让封板质量分错算。归一化到 `HH:MM:SS`。

---

## P1 — 架构基础（详细 plan 见 p1-architecture-foundations.md）

把当前 1688 行的 jvquant 适配器拆掉，建立可扩展的工程地基：

1. **`MarketDataAdapter` Protocol** — 显式接口契约，新加适配器立刻能查出漏实现。
2. **拆分 `jvquant_market_data.py`** — 拆成 queries/parsers/scoring/data_quality/adapter 5 个模块。
3. **评级阈值外置到 `config/candidate_grading.yaml`** — 让 P4 反馈闭环能自动调参。
4. **统一 `aegis_alpha.clock`** — 5 处重复的 `_now()` 收一处。
5. **MCP 单例 adapter + store** — 用 FastMCP lifespan 注入，避免每次工具调用重建。
6. **jvQuant 调用超时 + 简单 token bucket 限流** — 防止 agent loop 烧 quota。
7. **项目级 logger** — `aegis_alpha.logging` 统一 getLogger，关键路径打 INFO。
8. **SQLite schema 迁移机制** — `schema_versions` 表 + 顺序迁移文件。
9. **`_query_cache` 加 TTL** — 30s 默认。
10. **runner 重连指数退避 + 抖动**。
11. **修 SKILL.md 残留路径**。

---

## P2 — 评级核心数据补全（详细 plan 见 p2-grading-core-signals.md）

把评级体系从「单股语义查询拼凑」升级为「板块/梯队/情绪三维结构化输入」：

1. **`ThemeLeaderResolver`** — 用涨停时间、连板高度、封单额、是否最高板综合识别板块龙头；落 `theme_leaders` 表；对外暴露 `get_theme_leaders(theme)`。
2. **`LimitUpLadder`** — 计算每只股票的连板高度（往前回溯 N 日涨停），区分首板/二板/三板/...；落 `limit_up_ladder` 表；候选契约新增 `previous_consecutive_boards` 字段。
3. **`MarketEmotionGauge`** — 升级 `MarketSentimentGate`：增加昨日涨停今日溢价、昨日连板生死、首板/连板比、晋级率、空间板高度 5 个核心指标。
4. **`AuctionAnalyzer`** — 9:20 vs 9:25 竞价演变（撤单率、加速度），区分抢筹/出货；新增 `get_auction_analysis(symbol)` 工具。

---

## P3 — 持续工作流（待展开 plan）

把工具从「单次查询」升级为「跨时点连续工作流」。Scope：

- **盯盘列表持久化** — `watchlists` 表（owner、symbols、created_at、expires_at、状态历史）；`create_watchlist / update_watchlist_state / diff_watchlist / close_watchlist` 4 个 MCP 工具。
- **分歧→一致追踪** — 对每只候选记录 intraday seal/break timeline；落 `intraday_seal_events` 表；`get_seal_timeline(symbol)` 工具；`THEME_DIVERGENCE` 事件。
- **复盘报告生成** — `generate_daily_review(trading_day)` / `generate_weekly_pattern_report(start, end)` 自动汇总候选 + 评级 + outcome。
- **告警机制** — runner 检测到关键 event 时写 `agent_alerts` 表；MCP 提供 `get_pending_alerts / ack_alert`；可选 macOS notification hook。
- **板块强度排行** — `get_top_themes_today(limit)` / `get_theme_rotation(lookback_days)`。

任务列表估算：12-15 个 task。等 P2 完成（确认 leader/ladder 接口稳定后）再写步级 plan。

---

## P4 — 反馈闭环（待展开 plan）

把 `record_candidate_outcome` 的数据反馈进评级。Scope：

- **历史候选回填脚本** — `backfill_candidates(start_day, end_day)` 把过去 N 天的二板候选按当日规则重跑落库，建立训练数据。
- **失败归因** — outcome 落库时自动打标签（同板崩 / 大盘崩 / 竞价高开过多 / 首封太晚 / 龙头炸板）；落 `outcome_attributions` 表。
- **`three_year_*` placeholder 兑现** — 用真实 outcomes 计算每只股票的历史触板成功率、次日溢价率。
- **回测框架** — `backtest_grading_rule(rule_changes_yaml, start_day, end_day)` 在历史数据上跑修改后的评级规则，对比 grade × outcome 的胜率/盈亏比。
- **自动阈值建议** — 对纠错 proposal 的 `STRATEGY_ERROR` 类，跑回测验证「user 建议的阈值改动是否真的提升胜率」，提案带数据决策。

任务列表估算：15-20 个 task。依赖 P3 的 outcomes 持续记录链路。

---

## P5 — 数据维度扩展（待展开 plan）

补打板研究的关键外部数据。Scope：

- **龙虎榜适配器** — 接 jvQuant 龙虎榜接口或外部源；落 `dragon_tiger_records` 表；`get_dragon_tiger(symbol, trading_day)` / `get_active_seats_today()` 工具；游资席位识别（章盟主、孙哥、欢乐海岸、炒股养家等白名单）。
- **跌停池 / ST 板** — `get_limit_down_pool()` / `get_st_pool()`；`MARKET_BOTTOM_REVERSAL` 反向情绪事件。
- **涨停原因细分** — 业绩/政策/题材/游资 4 类分类器；候选契约新增 `limitup_driver_type`。
- **分时形态识别** — T 字板/一字板/烂板/平台突破/假突破识别；候选契约新增 `intraday_pattern`。
- **资金流分时切片** — 首封前 5 分钟 / 开板后 1 分钟 / 尾盘 30 分钟的资金分流。

任务列表估算：18-22 个 task。

---

## P6 — 进阶事件与生态（待展开 plan）

把单股事件升级为板块/跨周期事件，并搭历史层。Scope：

- **板块事件** — `THEME_LEADER_BREAK_BOARD` / `THEME_DIVERGENCE` / `SECTOR_ROTATION`。
- **跨周期校验** — 周线/月线视角；`get_weekly_position(symbol)`；候选契约新增 `weekly_health_score`。
- **相似形态搜索** — `find_similar_setups(symbol, lookback_days, similarity_threshold)`；用结构化指标（连板高度+板块+封单+情绪）做向量化匹配。
- **次新股专用通道** — `get_new_stock_candidates()`；按上市天数和流通市值分层。
- **停牌/复牌处理** — `suspended_stocks` 表；复牌特殊处理。
- **Parquet 历史层** — pyarrow 落 minute bars + lv2 trades + lv10 snapshots；DuckDB 查询入口。
- **假设分析** — `simulate_outcome(symbol, hypothesis)`。

任务列表估算：20-25 个 task。

---

## 交叉关注

每个阶段都要遵守的工程纪律（避免在每个 plan 里重复）：

- **TDD** — 所有新功能先写失败测试再实现；当前测试覆盖率不到 50%，每个 plan 都要顺手补现有代码的测试。
- **无 mock 兜底污染** — 适配器返回 mock 数据时 `data_mode` 必须是 `mock` 或 `unavailable`，禁止 live 适配器静默返回 mock 让 agent 误判。
- **每信号带 `data_quality`** — 新加任何信号字段，必须同时填 `SignalMetadata`（source/source_field/timestamp/confidence/usable_for_grading/limitations/evidence）。
- **MCP 输出兼容** — 已发布的 tool 不删字段、不改字段类型；新字段加默认值。
- **每改一处评级逻辑必须写复盘** — P4 之后所有规则改动同时跑回测，commit 信息引用回测结果。
- **频繁 commit** — 每个 task 一次 commit；不在 plan 任务之外做无关重构。

---

## Self-Review Checklist

P0/P1/P2 详细 plan 已落，逐条核对：

- [x] **正确性 bug 全覆盖** — speed_pct / 板种涨停 / 线程安全 / 时间格式（4 项 → P0 4 个 task）
- [x] **架构 bug 全覆盖** — Protocol / 拆分 / 阈值外置 / 时钟 / 单例 / 超时 / 限流 / 日志 / 迁移 / 缓存 TTL / 重连 / SKILL 路径（12 项 → P1 11 个 task，超时和限流合并一个 task）
- [x] **核心功能缺失** — 龙头 / 连板 / 情绪 / 竞价（4 项 → P2 4 个 task）；盯盘 / 分歧追踪 / 复盘 / 告警 / 板块排行（5 项 → P3 scope）；反馈闭环 4 项 → P4 scope；龙虎榜/跌停/原因/形态/资金分时 5 项 → P5 scope；板块事件/跨周期/相似/次新/停牌/Parquet/假设 7 项 → P6 scope
- [x] **依赖关系无环** — 见依赖图

未展开的 P3-P6 plans 在「待展开」状态，标准是：等其前置阶段完成、接口稳定后再写步级 plan，避免在不稳定接口上写死代码示例。
