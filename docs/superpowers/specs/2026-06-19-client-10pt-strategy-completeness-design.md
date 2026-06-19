# client_10pt 策略落地完整度设计

Date: 2026-06-19
Status: Approved (design), pending implementation plan

## 目标

让 `config/strategy_priors/client_10pt.yaml` 定义的 10 点二板买点策略,每一条都能被 agent 逐条走查:真值用真值、代理明标代理、缺失显式标注。零采购达成"策略可落地"的数据层。

## 设计原则

沿用项目既有约定:

- **facts-only**:程序只给事实,不给评分/概率/grade;agent 做判断。
- **显式 caveat**:拿不到的数据明标 `unavailable`;代理数据明标 `is_exchange_truth: false`。
- **many small files**:新数据源各自独立 adapter 目录,低耦合。
- **失败降级**:外部源(AkShare/巨潮)挂了或限频返回 `data_mode: unavailable` + caveat,绝不拖垮主链(沿用 runner "advisory, never kill the cycle")。
- **immutability**:实时路径与离线 replay 路径共用同一买点状态机,避免双实现漂移。

## 背景:四路数据源调研定论

- **#6 盘口实时大单主动买入占比**:A 股交易所 BS flag 真值仅付费 Level-2 专线分发。jvQuant 官方文档铁证逐笔成交只有 时间/编号/价格/数量 4 字段,无方向;委托队列无委托编号无法撮合还原。Tushare L2 大概率 T+1 非实时且方向是 tick-rule 推断,¥5k 买不到实时真值。真值实时只剩 Wind ¥万级 / 恒生 / 券商直连。
- **#8 全市场板块宽度**:AkShare 免费可达接近真值 + 两周回溯。两坑:无涨停家数直字段(需自建 成分股×涨停池 join);概念体系不一致,打板圈主流用同花顺 THS 体系(东财体系偏差 15–30%)。
- **#3/#10 财联社/新闻**:爬原文极高合规风险(违反 CLS 协议 + AkShare 封装 2026/5 已失效)。合规替代 = 巨潮资讯公告(免费)+ Tushare 新闻。

jvQuant 不可抛弃:它是实时引擎(lv2 websocket、盘口、语义查询、盘中买点监控),与 Tushare 互补非替代。

## 策略 10 点 × 现状 × 本设计目标

| # | 策略条件 | 现状 | 本设计后 | 真值/代理 |
|---|---------|------|---------|----------|
| 1 | 近10日均额>50亿 | ✅ 真值 | 不变 | 真值 |
| 2 | MA5斜率30–60° | ⚠️ 配置/实现不一致 | 策略层移除,数据层保留 | 弃用 |
| 3 | 板块两周持续性 | ⚠️ 仅市场内 | + 合规新闻佐证 | 市场内真值+新闻代理 |
| 4 | T-1缩量 | ✅ 真值 | 不变 | 真值 |
| 5 | T日带量过前高 | ✅ 真值 | 不变 | 真值 |
| 6 | 盘口实时大单买入占比 | ❌ 无 | tick-rule 代理(明标非真值) | 代理 |
| 7 | 回踩缩量重新上冲=买点 | ⚠️ runner 已部分实现 | 核实+补缺+固化 | 真值 |
| 8 | 同板块共振 | ⚠️ packet-local 代理 | 全市场宽度(THS) | 全市场真值 |
| 9 | 监控时段 | ⚠️ 参数支持 | 固化为默认 | 真值 |
| 10 | 财联社消息 | ❌ placeholder | 合规替代(公告/新闻) | 代理(非电报) |

---

## 实施方案:方案 A — 按"配置 → 数据 → 实盘"分三波

### 第 1 波:配置债清理(零依赖)

#### #2 — MA5 斜率不一致清理

**矛盾**:`client_10pt.yaml` 第 12-16 行 MA5 阈值仍存在,但 SKILL.md 多处声明"本期移除",`server.py:715/778` 及测试已断言它不该出现在 active strategy。

**影响面**(已全量 grep):`models.py`、`candidates.py`、`mock/jvquant adapter`、`client_facts.py`、6 个测试文件。

**决策**:策略层移除,数据层保留。
- `client_10pt.yaml`:删除 `ma5_slope_degrees` threshold 块。
- 保留 `ma5_slope_degrees` 计算函数(`measurements/client_facts.py`)与字段(`models.py`)作为中性未激活 fact——不删字段,避免破坏 candidate 契约和测试。
- `test_strategy_priors.py`:反转现有断言(当前断言 MA5 *在* thresholds 里,改为断言它*不在*)。
- 验证 `server.py` 既有的 "MA5 not part of active strategy" 逻辑与配置最终一致。

#### #9 — 监控时段固化

**现状**:`runner.py` 的 `monitor_windows_from_config` 已支持窗口,需确认默认值是否为策略第 6 点的 9:30–9:50 / 11:10–11:30。

**决策**:
- 把两个监控窗口固化为 runner 配置默认值。
- SKILL.md 把这两个窗口写成 replay/live 工具的默认 `window_start/window_end`。
- 纯配置 + 文档,无逻辑改动。

---

### 第 2 波:新数据源接入(facts-only + 显式 caveat)

#### #8 — 全市场板块共振宽度

**新增模块** `adapters/sector_breadth/`(AkShare 源),独立目录低耦合。

| 能力 | 实现 | 输出 facts |
|------|------|-----------|
| 当日板块宽度 | 成分股列表 × 当日涨停池 join | 每板块:涨停家数 / 成分总数 / 涨停占比 / 上涨家数 |
| 两周持续性 | 14 日滚动逐日 join 历史涨停池 | 异动天数 / 累计涨停 / 最大单日 / 持续性 label |

**决策**:
1. **概念体系选 THS(同花顺)**:打板圈主流,东财体系偏差 15–30%。建 `code→THS概念` 本地静态映射表,定期刷新。
2. **限速防 429**:遍历 200+ 板块加 sleep;盘后批量预算 + 本地缓存;盘中只用板块涨跌幅轻量代理,不全市场遍历。
3. **数据质量 caveat**:输出带 `concept_system: "ths"` + `coverage` + `data_source: "akshare"`,明标非交易所官方归类。

**新 MCP 工具**:
- `get_market_sector_breadth(trading_day, theme)`
- `get_sector_breadth_continuity(theme, as_of_day, lookback_days)`

**与现有关系**:升级 `get_theme_continuity` 的数据基础但不删旧工具——新工具是全市场版,旧的留作 jvQuant 语义版,agent 可对照。

#### #3 / #10 — 合规新闻 / 题材消息面对齐

**新增模块** `adapters/news_alignment/`,走合规替代(放弃财联社原文)。

| 源 | 内容 | 合规风险 |
|----|------|---------|
| 巨潮资讯公告(免费,默认) | 政策/公司公告 | 极低(完全公开) |
| Tushare news(可选,~¥300 积分) | 主流财经新闻 | 中(Tushare 有授权) |

**输出**:`news_alignment` facts —— 某题材/个股近 N 日是否有公告/新闻命中(关键词匹配),带 `source`、`matched_count`、`alignment_strength: weak/medium/none`。

**决策**:
1. **明标"非财联社原文"**:`caixin_alignment` 字段保持 placeholder;新增 `news_alignment` 合规字段;SKILL 写清"公告/新闻代理,非财联社电报"。
2. **弱证据定位**:新闻对齐仅作题材持续性辅助佐证,不作主信号。
3. **Tushare news 可插拔**:巨潮免费源默认;Tushare 作为可选增强,未配置 token 则仅用巨潮 + 显式标注覆盖度降低。

**新 MCP 工具**:`get_news_alignment(symbol_or_theme, lookback_days)`。

**为何放弃爬财联社原文**:法律(违反 CLS 用户协议、付费内容未授权抓取有民事诉讼+停止侵害函风险)+ 可靠性(免费封装 2026/5 已失效、逆向接口随时被封)+ 性价比(#10 策略权重最低且声明本期不接)。合规替代对"政策/公告驱动型题材有无消息面支撑"够用且合法。

---

### 第 3 波:实盘买点完整化 + #6 资金确认代理

#### 现状(核实后真相)

`runner.py:364 detect_buypoints_in_window` 已实现窗口内实时买点:已读监控窗口、从 tick buffer 聚合分钟 bar 驱动状态机 `replay_buypoint`、过前高(fact-first + 开盘窗口 fallback)→ 触发 → 写 paper alert + macOS 通知 + dedup、明确只读绝不下单。

故 #7 是"核实完整 + 补资金确认层",非从零重写。

#### #7 — 买点链完整化(策略第 4 点)

**三段式**:带量过前高(#5)→ 回踩砸盘缩量 → 重新上冲 = 买入预警点。

**决策**:
- 审计 `buypoint_state_machine` 三段转移是否齐全(尤其"回踩缩量"段的量能判定)。
- 确认实时路径(buffer→分钟bar)与离线 replay 路径**共用同一状态机**(单一真相,避免漂移)。
- 有缺口补齐;已完整则加测试固化。优先核实+补缺,不另起炉灶。

#### #6 — tick-rule 大单买入占比代理(明标非真值)

项目唯一"妥协层",诚实标注必须做到位。

**来源**:jvQuant lv2 逐笔成交(时间/编号/价格/数量,无方向)→ 本地 tick-rule 推断:价格较上一笔↑=主动买,↓=主动卖,平=中性;大单阈值(如 >50万/>100万)算大单主动买入金额占比。

**诚实标注三重保险**:

| 保险 | 做法 |
|------|------|
| 字段命名 | `tick_rule_big_buy_ratio_proxy`,绝不叫 `big_order_buy_ratio` |
| 元数据 | 输出带 `is_exchange_truth: false`、`method: "tick_rule"`、`accuracy_caveat` |
| 封板虚高警告 | tick-rule 在封板博弈时系统性虚高;价格接近涨停时输出 `sealing_distortion_warning`:"封板时高估主动买入,不可信" |

**定位**:策略第 3 点"资金确认"层,弱证据。买点主链 #5→#7 不依赖它即可触发;#6 只回答"这次上冲有无大单代理迹象",封板时主动降级。

**新 MCP 工具**:`get_tick_rule_orderflow_proxy(symbol, window_start, window_end, big_trade_threshold)`,与现有 directionless 的 `sample_realtime_large_trade_proxy` 互补(一个给金额,一个给推断方向,都明标代理)。

#### 接入买点链

买点触发时附带 #6 代理 facts 作为上下文(不作触发条件):

```
buy_point_alert {
  trigger: 过前高→回踩缩量→重新上冲 (主链, 真值)
  context.orderflow_proxy: tick_rule_big_buy_ratio_proxy + 三重caveat (弱证据)
}
```

---

## 测试策略

沿用项目 TDD 约定(RED→GREEN→REFACTOR),每波独立可测:

- **第 1 波**:配置一致性测试(`test_strategy_priors.py` 断言反转)、监控窗口默认值测试。
- **第 2 波**:新 adapter 的 facts-only 输出测试、失败降级(`data_mode: unavailable`)测试、caveat 字段存在性测试。mock 优先,真实 AkShare/巨潮探测作为可选集成测试。
- **第 3 波**:买点状态机三段式转移测试、实时与离线路径一致性测试、#6 tick-rule 代理的封板虚高警告测试、命名/元数据 caveat 测试。

全套测试基线:当前 `581 passed, 9 skipped`。每波完成后不得回归。

## 验收标准

三波完成后:

- **数据层**:10 点中 8 点真值,#6/#10 为诚实代理(权重最低 + A 股结构性墙)。数据完整度 ~90%,剩余 10% 非工程债。
- **主触发链** #5→#7 全真值且实盘可跑。
- 全套测试不回归,新增能力均有测试覆盖。

## 二期路线图(本次不实施,固化为可追踪验收基准)

明确"数据齐 ≠ 策略验证完成",剩余距离不在数据而在验证:

- **二期 A(强烈建议,零成本)**:#3+#4 闭环验证 —— 持久化 agent 收盘选的 TopN,次日早盘自动对照实际触发打分。回答"策略到底有无 alpha"。优先级高于买 #6 真值。
- **二期 B(可选,花钱)**:#6 Wind ¥万级真值 —— 等闭环验证证明策略有 alpha 后再投。
- **样本量坎**:策略结论需 ≥10 交易日回放样本才脱离 exploratory。
- **实盘 vs 回放坎**:#7 实时买点的盘中稳定性/延迟/断线重连只有真实交易日暴露。

一句话:三波让程序"配得上"策略;闭环验证(#3+#4)才让你"信得过"策略。
