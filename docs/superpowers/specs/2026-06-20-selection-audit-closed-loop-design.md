# 选股审计闭环验证设计 (二期 A: #3+#4)

Date: 2026-06-20
Status: Approved (design), pending implementation plan

## 目标

闭合 client_10pt 策略的"验证回路":持久化 agent 收盘时的**选股决策**(选了谁、落选谁、相对理由、缺失数据 caveat),次日早盘自动对照**目标日盘中触发事实 + 次日结果**,回答系统存在的根本问题——**agent 按策略选的票,到底比朴素基准强吗?**

这是二期最高优先级、零采购、纯工程项。比花 ¥万级买 #6 真值优先级更高:先证明策略有 alpha,再为它投钱。

## 背景:闭环基建已大半就位

核对后,现有零件(不重建):
- `AgentReview` 持久化每只票的 grade/promotion_likelihood(payload.per_symbol)
- `CandidateOutcomeReview` 存次日结果(开盘/最高/封板)
- `feedback/agent_scorecard.py` 的 `extract_predictions` + `build_judgment_rows` + `compute_scorecard` 已按 `(symbol, trading_day)` 自动 join 预测↔结果,算 Brier/校准度
- `get_agent_judgment_scorecard`、`get_strategy_decision_packet`、`get_second_board_next_day_outcomes` MCP 工具已存在

真正的缺口:
- **#3**:`AgentReview` 存了"打几分",但没存"**选股动作**"——从 M 个候选选了这 TopN、落选 near-miss、相对理由、caveat。SKILL 有"反机械排序"规则但**无任何持久化**。
- **#4**:现有 scorecard 比"预测 grade vs 次日封板"。#4 要更细:"**收盘选择 vs 目标日 09:31–10:00 触发事实 + 次日结果**"——验证策略下注的盘中触发形态是否出现。

所以本设计 = "**持久化选股动作 + 自动对照目标日触发**",不是重建 scorecard。

## 设计原则

沿用项目既有约定:facts-only(审计不含 grade/score/pass);显式 caveat;失败降级(上游拿不到 → unavailable,不脑补,不拖垮);many small files / 单一职责(审计独立于 review);immutability。

## 四个已定决策(brainstorm 输出)

1. #3 选股审计走 **agent 显式调 `record_selection_audit` 工具**(非程序拦截)。
2. #4 对照口径 **两者都要**:盘中触发(买点出现没)+ 次日结果(触发后赚了没)。
3. 触发方式 **两都要**:先 MCP 工具(核心逻辑),再接 runner 次日自动跑。
4. **反机械排序基准纳入审计**:record 时算三朴素基准 TopN,标记 agent 选择是否机械等同。

---

## 1. 数据模型(新表 selection_audits + migration m0008)

一条审计 = 某收盘日 agent 的一次完整选股决策。

### 新表 `selection_audits`

| 字段 | 类型 | 含义 |
|------|------|------|
| `audit_id` | TEXT PK | 幂等哈希(as_of_day + 排序后 picks symbols) |
| `as_of_day` | TEXT | 收盘日(选股基准日) |
| `picks_json` | TEXT | TopN: `[{symbol, rank, relative_reason, caveats[]}]` |
| `rejected_json` | TEXT | 落选 near-miss: `[{symbol, why_rejected, beat_by}]` |
| `baseline_json` | TEXT | 三基准 TopN: `{seal_amount[], seal_ratio[], first_seal_time[]}` |
| `equals_baseline` | INTEGER | agent TopN 是否等同任一基准(反机械排序, 0/1) |
| `confidence_label` | TEXT | exploratory / low / medium |
| `candidate_pool_size` | INTEGER | 当时候选池总数 M |
| `provider` | TEXT | LLM provider |
| `model` | TEXT | LLM model |
| `created_at` | TEXT | 写入时间 |

### Pydantic 模型(models.py)

- `SelectionPick`: `symbol: str`, `rank: int`, `relative_reason: str = ""`, `caveats: list[str] = []`
- `RejectedCandidate`: `symbol: str`, `why_rejected: str = ""`, `beat_by: str = ""`
- `SelectionAudit`: `audit_id, as_of_day, picks: list[SelectionPick], rejected: list[RejectedCandidate], baseline: dict, equals_baseline: bool, confidence_label: str, candidate_pool_size: int, provider, model, created_at`

全部 facts-only,**不含** grade/score/pass/probability/reject 字段(哲学守卫)。

### 关键设计点

1. **audit_id 幂等**:同 as_of_day + 同组 picks → 同哈希 → 重复 record 是 upsert(沿用 backtest `_run_id` 模式)。
2. **equals_baseline 内生**:record 时把 agent TopN 与三基准 TopN 比对并标记——固化"反机械排序"守卫。
3. **confidence_label 守卫**:累积审计 <10 交易日 → 强制 exploratory。
4. **migration m0008**:沿用 db_migrations_files/ 模式,`CREATE TABLE IF NOT EXISTS selection_audits`。
5. 审计表与 `agent_reviews` **分开**:选择归选择,打分归打分。

---

## 2. 三个 MCP 工具

### 工具 1 — `record_selection_audit`(写, #3)

```
record_selection_audit(as_of_day, picks_json, rejected_json="",
                       candidate_pool_size=0, provider="", model="") -> dict
```

- agent 选完 TopN 调用,传 picks(含相对理由+caveat)、落选 near-miss。
- 程序内部自动算三朴素基准(从当天候选池事实的封单额/封成比/首封时间各取 TopN),与 agent picks 比对 → 填 `equals_baseline`。
- confidence_label:查已累积审计天数,<10 强制 exploratory。
- 算幂等 audit_id,upsert 入表。
- 返回:存入的审计 + **即时反机械排序提醒**(equals_baseline=1 时明确"你的 TopN 等同某基准,未体现额外 alpha")。

### 工具 2 — `get_selection_audit`(读)

```
get_selection_audit(as_of_day) -> dict
```
取某日审计,facts-only。无记录 → `data_mode: unavailable`。

### 工具 3 — `get_selection_trigger_validation`(对照闭环, #4)

```
get_selection_trigger_validation(as_of_day, target_day,
                                window_start="09:31", window_end="10:00") -> dict
```

闭环的"合"。三步 join:
1. 拉 as_of_day 的 selection_audit(选了谁)。
2. 对每只 pick 调 `get_strategy_decision_packet`(已有)→ 盘中触发事实(开盘窗口过前高没、买点触发没)。
3. 对每只 pick 取次日结果(已有 `get_second_board_next_day_outcomes`/`CandidateOutcomeReview`)→ 触发后赚了没。

输出每只 pick 一行:`{symbol, agent相对理由, 盘中是否触发, 触发时间, 次日开盘/最高/封板, 命中判定}`。
汇总:`triggered_count/total`、agent 推理命中率、**对比基准**(同样跑三基准 TopN 的触发率,看 agent 是否赢基准)。
诚实标注:样本 <10 交易日 → exploratory;窗口默认策略的 09:31–10:00。

### 关键设计点

1. 三工具 facts-only + 失败降级(任一上游拿不到 → 该字段 unavailable,不脑补,不拖垮)。
2. `get_selection_trigger_validation` **只读纯组合**,不写库(审计已持久化,这层实时 join)。
3. 复用而非重建:decision_packet、next_day_outcomes、三基准计算都已存在。

---

## 3. runner 次日自动接入

把对照从"agent 手动调"升级到"次日开盘自动跑 + 告警"。沿用 `detect_buypoints_in_window` 的 "advisory, never kill the cycle" 模式。

**触发逻辑**(run_once 周期内):
```
当满足:
  - 当前在交易日开盘后(target_day = today)
  - 存在 as_of_day = 上一交易日 的 selection_audit
  - 该 (as_of_day → target_day) 今天还没验过(dedup)
→ 调 get_selection_trigger_validation(昨收audit, today)
→ 写 SELECTION_VALIDATION AgentAlert + macOS 通知
```

### 关键设计点

1. **窗口对齐**:验证在 09:31–10:00 之后跑(等开盘触发数据齐)。新增配置 `selection_validation.after: "10:00"`。
2. **dedup**:同 (as_of_day, target_day) 一天只验一次,dedup key `selection_validation:{as_of}:{target}`。
3. **advisory 隔离**:验证失败/异常绝不杀 runner 周期(try/except 吞,沿用 `_collect_sector_events`/`detect_buypoints_in_window` 惯例)。
4. **新告警类型** `SELECTION_VALIDATION`:带触发率 + 是否赢基准 + exploratory 标记,走现有 `get_pending_alerts` 通道。
5. **只读 runner**:钩子只读审计 + 写 AgentAlert,绝不下单、绝不改审计。

### 新增配置(config/runner.yaml)
```yaml
selection_validation:
  enabled: true
  after: "10:00"
```

### 诚实边界
runner 自动验证只在真实交易日盘中有意义(要 target_day 盘中触发数据)。盘后/非交易日钩子静默跳过。工程把钩子搭好,真实验证质量仍要等真实交易日 + 样本累积。

---

## 4. 测试策略

沿用 TDD + 哲学守卫 + 基线不回归(当前 601 passed / 7 skipped)。

**数据模型层**:模型构造测试;哲学守卫(model_dump 不含 grade/score/pass/probability/reject);migration m0008 建表测试。

**纯计算层(feedback/selection_audit.py)**:audit_id 幂等(同输入同 ID,变则变);三基准对比 + equals_baseline(等同基准→1,全不同→0);confidence_label(<10天→exploratory,≥10→可 low/medium);near-miss/相对理由结构。

**MCP 工具层**:record 写入+即时反机械排序提醒+幂等 upsert;get 取到/unavailable;trigger_validation 用 monkeypatch 假 adapter 注入(不真连 jvQuant),断言三方 join、触发率、基准对比、exploratory、上游 unavailable 降级。

**runner 接入层**:钩子 10:00 后+有昨收审计+未验过→触发(monkeypatch 时间+假 audit);dedup;**advisory 隔离**(验证抛异常→runner 不挂,沿用现有 buypoint 隔离测试);非交易日/无审计→静默跳过。

**集成/回归**:端到端 happy-path(record→get→validation);全套回归 601+新增,零 FAIL。

## 验收标准

- 闭环端到端跑通:录入选择 → 次日对照盘中触发+结果 → 告警。
- 反机械排序守卫固化为数据(equals_baseline)+ 即时提醒。
- 样本不足强制 exploratory。
- facts-only 哲学守卫通过。
- 全套测试不回归。

## 范围外(后续)

- #6 Wind ¥万级真值(等本闭环证明策略有 alpha 后再投)。
- 样本量累积(需真实 ≥10 交易日,工程无法替代)。
- 实盘稳定性(只有真实盘中暴露)。
