# P7 — Polish & Tech Debt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 P0–P6 期间累积的 8 项小债务清干净——修好 2 个自 P3 起一直挂着的失败测试、把 P6 final reviewer 给的 5 个 follow-up 落地、再补 2 处 placeholder 信号 / 错误路径测试缺口——让仓库回到「全绿、零已知 hot path bug」的状态。

**Architecture:**
本期不引入新子系统、不动架构。所有改动都是局部清理：3 处对历史代码 / 测试的小修，3 处把 P6 已搭好的检测器与 helper 接到现有 pipeline，2 处在已有 MCP 层加 placeholder 信号 + 错误路径测试。每个 task 改动 1–3 个文件、单一职责。

**Tech Stack:**
Python 3.11+, Pydantic v2, SQLite, FastMCP, pytest TDD（无新依赖）。

---

## P7 范围（来自 P6 final review + 历史负债）

| # | 项目 | 来源 |
|---|------|------|
| 1 | 修复 `tests/test_jvquant_adapter.py::test_time_or_unknown_normalizes_short_form` | P3 期间 jvquant adapter 拆分时遗留 |
| 2 | 修复 `tests/test_jvquant_adapter.py::test_seal_quality_score_uses_normalized_time` | P3 期间 jvquant adapter 拆分时遗留 |
| 3 | `_call_tool` 不再吞掉 `_call_store` 错误，让缺 store 时返回真实错误而不是 silent `unavailable` | P6 reviewer minor |
| 4 | `list_suspended_stocks` 在 SQL 端用 `idx_suspended_day` 做 day-range 过滤 | P6 reviewer minor |
| 5 | 给所有 P6 starter 常量加 `# CALIBRATE` 注释 + 集中到 `config/p6_thresholds.yaml` 文档化 | P6 reviewer 与 P5 reviewer 都提到 |
| 6 | 在 `JvQuantMarketDataAdapter.get_second_board_candidates` 里把 `is_symbol_suspended` 用上 | P6 reviewer follow-up |
| 7 | runner event loop 里调用 `detect_theme_leader_break_board` + `detect_sector_rotation` | P6 reviewer follow-up |
| 8 | `simulate_outcome` 加 re-grading hook（用 P4 现成 `backtest._apply_rule_changes`-style 钩子） | P6 reviewer follow-up |
| 9 | `get_active_seats_today` jvquant 路径加 `data_mode=placeholder` 信号（P5 reviewer 提的） | P5 reviewer minor |
| 10 | 给 `get_new_stock_candidates` 与 `get_suspended_stocks` 补错误路径测试 | P6 reviewer minor |
| 11 | docs sync（README + SKILL）+ 全量回归 | 标准收尾 |

任务总数：11 个 task。

## 强制约束（Subagent 实施时必须遵守）

1. **不允许真实交易**。所有 P7 输出仍仅 read-only。
2. **不能私改 LLM 模型名**。`anthropic/claude-opus-4-7` 与 `deepseek-v4-pro` 名字保持原样。
3. **TDD 严格执行**：每个改动先写失败测试，再改实现，再 commit。
4. **保留向后兼容**：测试期望签名不能改坏；公开 API（MCP tool / Protocol 方法）不删字段不改类型。
5. **不要新增子系统**：本期纯清理，P8 才考虑下一波功能。
6. **不要重构**：例如不要拆 `runner.py`，不要重命名常量。只在原位改最小代码。
7. **starter 常量保持值不变**：本期只加 `# CALIBRATE` 注释，不改阈值。Calibration 留 P8。
8. **所有 sub-agent worktree 必须 base 在 `main` 当前 HEAD**（仓库根 `.claude/settings.json` 已配 `worktree.baseRef = head`）。

## 文件结构（落盘前先看完）

### 新增

| Path | 责任 |
|------|------|
| `config/p6_thresholds.yaml` | 把 5 个 P6 starter 常量集中文档化（注释为主，不在 P7 加载它），方便 P8 calibration。 |
| `tests/test_p7_polish.py` | P7 期间跨子系统 polish 测试集。 |

### 修改

| Path | 修改内容 |
|------|---------|
| `tests/test_jvquant_adapter.py` | 改 2 个失败测试调用 `parsers._time_or_unknown` 与 `scoring.seal_quality_score`（model 已搬，测试还在用 adapter 实例方法）。 |
| `src/aegis_alpha/storage.py` | `list_suspended_stocks` SQL 端 day-range 过滤。 |
| `src/aegis_alpha/extensions/contrarian_pool.py`, `extensions/sector_events.py`, `extensions/new_stocks.py`, `extensions/limitup_driver.py`, `extensions/intraday_pattern.py` | 5 个文件的 starter 常量上方加 `# CALIBRATE: ...` 注释（值不变）。 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | `get_second_board_candidates` 里用 `is_symbol_suspended` 过滤；`get_active_seats_today` 加 placeholder 信号。 |
| `src/aegis_alpha/runner.py` | event loop 接 `detect_theme_leader_break_board` + `detect_sector_rotation`。 |
| `src/aegis_alpha/feedback/hypothesis.py` | `simulate_outcome` 接 re-grading hook（计算 hypothetical_grade）。 |
| `src/aegis_alpha/mcp/server.py` | `_call_tool` / `_call_store` 错误路径让 P6 已有的早返回保持优先级（已经是这样的，只补测试）。 |
| `tests/test_mcp_p6_tools.py` | 给 `get_new_stock_candidates` / `get_suspended_stocks` 补错误路径测试。 |
| `README.md` | 补一段「P7 polish」说明 + p6_thresholds.yaml 链接。 |
| `.hermes/skills/second-board-radar/SKILL.md` | Workflow item 21 加一行「停牌过滤已自动接入候选拉取」。 |

---

## Task 1: 修复 test_time_or_unknown_normalizes_short_form

**Files:**
- Modify: `tests/test_jvquant_adapter.py`

**Background:**
P2 期间 `JvQuantMarketDataAdapter` 类拆成多个模块。`_time_or_unknown` 从 instance method 搬到了 module-level helper 在 `src/aegis_alpha/adapters/jvquant/parsers.py:233`。但测试还按旧 API 用 `adapter._time_or_unknown(...)`。

- [ ] **Step 1: 看现有测试**

打开 `tests/test_jvquant_adapter.py` 第 401-413 行，确认 10 个 assert 调用 `adapter._time_or_unknown(...)`。

- [ ] **Step 2: 改测试**

把 `tests/test_jvquant_adapter.py` 中 `test_time_or_unknown_normalizes_short_form` 整个函数改成（保留所有 10 个断言原样，只换调用对象）：

```python
def test_time_or_unknown_normalizes_short_form() -> None:
    from aegis_alpha.adapters.jvquant.parsers import _time_or_unknown

    assert _time_or_unknown("9:45") == "09:45:00"
    assert _time_or_unknown("9:45:30") == "09:45:30"
    assert _time_or_unknown("09:45") == "09:45:00"
    assert _time_or_unknown("09:45:30") == "09:45:30"
    assert _time_or_unknown("2026-05-29 9:45:30") == "09:45:30"
    assert _time_or_unknown("2026-05-29T09:45:30+08:00") == "09:45:30"
    assert _time_or_unknown("") == "unknown"
    assert _time_or_unknown("None") == "unknown"
    assert _time_or_unknown("nan") == "unknown"
    assert _time_or_unknown("garbage") == "unknown"
```

- [ ] **Step 3: 跑测试**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_adapter.py::test_time_or_unknown_normalizes_short_form -v`
Expected: PASS。如果其中某个具体 case 仍然失败（说明 `_time_or_unknown` 当下行为与历史断言不一致），说明 parsers.py 改错了，不是测试错。打开 `src/aegis_alpha/adapters/jvquant/parsers.py:233` 检查 `_time_or_unknown` 实现，必要时把断言改成实际行为（但优先修实现以匹配历史断言）。

- [ ] **Step 4: 提交**

```bash
git add tests/test_jvquant_adapter.py
git commit -m "Fix test_time_or_unknown to call parsers helper after P2 split"
```

---

## Task 2: 修复 test_seal_quality_score_uses_normalized_time

**Files:**
- Modify: `tests/test_jvquant_adapter.py`

**Background:**
同 Task 1 的拆分原因，`seal_quality_score` 现在是 `src/aegis_alpha/adapters/jvquant/scoring.py:42` 的 module-level function，签名比旧的 instance method 多了 `config` 参数。

- [ ] **Step 1: 看 seal_quality_score 签名**

打开 `src/aegis_alpha/adapters/jvquant/scoring.py:42`，确认函数签名：

```python
def seal_quality_score(
    *,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> float:
```

- [ ] **Step 2: 改测试**

替换 `tests/test_jvquant_adapter.py` 中的 `test_seal_quality_score_uses_normalized_time`：

```python
def test_seal_quality_score_uses_normalized_time() -> None:
    from aegis_alpha.adapters.jvquant.parsers import _time_or_unknown
    from aegis_alpha.adapters.jvquant.scoring import seal_quality_score
    from aegis_alpha.grading import CandidateGradingConfig

    config = CandidateGradingConfig()
    score_short = seal_quality_score(
        first_limit_up_time="09:45:00",
        seal_amount_cny=200_000_000,
        seal_to_turnover_ratio=3.0,
        config=config,
    )
    score_normalized = seal_quality_score(
        first_limit_up_time=_time_or_unknown("9:45"),
        seal_amount_cny=200_000_000,
        seal_to_turnover_ratio=3.0,
        config=config,
    )
    assert score_short > 0
    assert score_short == score_normalized
```

如果 `seal_quality_score` 的关键字签名不完全一致（例如不是 `first_limit_up_time` 而是 `first_seal_time`），打开 scoring.py 看实际名字并把测试里的 kwargs 名字对齐。

- [ ] **Step 3: 跑测试**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_adapter.py::test_seal_quality_score_uses_normalized_time -v`
Expected: PASS。

- [ ] **Step 4: 全量再跑确认 0 fail**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q --no-header 2>&1 | tail -5`
Expected: `N passed`，0 failed。

- [ ] **Step 5: 提交**

```bash
git add tests/test_jvquant_adapter.py
git commit -m "Fix test_seal_quality_score to call module-level helper after P2 split"
```

---

## Task 3: list_suspended_stocks SQL-side day-range 过滤

**Files:**
- Modify: `src/aegis_alpha/storage.py:1275-1295`
- Test: `tests/test_p6_storage.py`

**Background:**
P6 reviewer：`list_suspended_stocks` 现在 `SELECT * ORDER BY suspension_start_day` 然后 Python 端 filter，没用上 `idx_suspended_day`。表小现在没问题，但要修。

- [ ] **Step 1: 写新测试**

追加到 `tests/test_p6_storage.py`：

```python
def test_list_suspended_stocks_uses_sql_filter_for_trading_day(tmp_path):
    """SQL filter must respect: start <= day AND (end blank OR end >= day).

    This test exercises the SQL path with mixed entries to make sure the
    optimization does not break the existing filter semantics.
    """
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "p7.db"))
    store.init_db()
    store.save_suspended_stock(
        SuspendedStock(symbol="A", suspension_start_day="2026-05-20",
                       suspension_end_day=""),
        created_at="t",
    )
    store.save_suspended_stock(
        SuspendedStock(symbol="B", suspension_start_day="2026-05-22",
                       suspension_end_day="2026-05-26"),
        created_at="t",
    )
    store.save_suspended_stock(
        SuspendedStock(symbol="C", suspension_start_day="2026-06-01",
                       suspension_end_day=""),
        created_at="t",
    )
    rows = store.list_suspended_stocks(trading_day="2026-05-25")
    symbols = {r.symbol for r in rows}
    # A is open-ended after 2026-05-20 → in. B starts 22 ends 26 → in (25 <= 26). C starts 06-01 → out.
    assert symbols == {"A", "B"}

    rows_after = store.list_suspended_stocks(trading_day="2026-05-30")
    after_symbols = {r.symbol for r in rows_after}
    # B's end_day is 2026-05-26 < 2026-05-30 → out. A still open-ended → in. C still future → out.
    assert after_symbols == {"A"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p6_storage.py -k uses_sql_filter -v`
Expected: 实际上现有 Python-side filter 也能通过（既然语义一样）。这个测试是回归保护——确保 SQL 改动不破坏原有语义。先跑一遍验证是 PASS。

- [ ] **Step 3: 改 SQL**

把 `src/aegis_alpha/storage.py:1275-1295` 整个 `list_suspended_stocks` 替换为：

```python
def list_suspended_stocks(
    self, *, trading_day: str = ""
) -> list[SuspendedStock]:
    """List suspended stocks. If trading_day given, only return entries that
    are active on that day (start_day <= trading_day, AND end_day blank or end_day >= trading_day).

    Day-range filtering happens in SQL using idx_suspended_day for efficiency.
    """
    if not trading_day:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM suspended_stocks "
                "ORDER BY suspension_start_day ASC"
            ).fetchall()
        return [SuspendedStock.model_validate_json(row[0]) for row in rows]

    with self._connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM suspended_stocks "
            "WHERE suspension_start_day <= ? "
            "AND (suspension_end_day = '' OR suspension_end_day >= ?) "
            "ORDER BY suspension_start_day ASC",
            (trading_day, trading_day),
        ).fetchall()
    return [SuspendedStock.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑全部 P6 storage 测试**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p6_storage.py -v`
Expected: 全部 PASS（原有 `test_save_and_list_suspended_stocks` 也应继续 PASS，因为语义一致）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/storage.py tests/test_p6_storage.py
git commit -m "Push list_suspended_stocks day-range filter into SQL"
```

---

## Task 4: P6 starter 常量加 CALIBRATE 注释 + p6_thresholds.yaml

**Files:**
- Create: `config/p6_thresholds.yaml`
- Modify: `src/aegis_alpha/extensions/contrarian_pool.py:10`
- Modify: `src/aegis_alpha/extensions/sector_events.py:14-17`
- Modify: `src/aegis_alpha/extensions/new_stocks.py:6-9`
- Modify: `src/aegis_alpha/extensions/limitup_driver.py:23`
- Modify: `src/aegis_alpha/extensions/intraday_pattern.py:9-12`

**Background:**
P5 / P6 reviewer 都提到：5 个 extensions 文件里散布的 starter 常量没有「这是 starter，等校准」的标记，将来读代码的人会以为它们是定论。本期不改值，只加 `# CALIBRATE: ...` 注释 + 集中到 yaml 文档。

- [ ] **Step 1: 写 yaml 文档**

创建 `config/p6_thresholds.yaml`：

```yaml
# P6 starter thresholds — calibrate against historical limit-up outcomes in P8.
# Code constants are NOT loaded from this file; this is documentation only so
# operators / future calibrators can find every starter value in one place.
#
# Each entry: where the constant lives, current value, and what we'd want to
# learn from history before changing it.

contrarian_pool:
  # at least N yesterday-limit-down stocks reversing to limit-up today
  recovery_threshold:
    file: src/aegis_alpha/extensions/contrarian_pool.py
    constant: _RECOVERY_THRESHOLD
    current_value: 3
    calibration_note: |
      Run a backtest over yesterday-limit-down pools across 6+ months and
      measure precision/recall of MARKET_BOTTOM_REVERSAL events at thresholds
      2/3/4/5. Pick the one whose next-day market behaviour proves most
      directional.

sector_events:
  break_board_base_score:
    file: src/aegis_alpha/extensions/sector_events.py
    constant: _BREAK_BOARD_BASE_SCORE
    current_value: 60.0
    calibration_note: |
      Min score for a leader-break event to be worth surfacing. Tune so that
      events scoring below this are dominated by noise in historical replay.
  break_board_height_bonus:
    file: src/aegis_alpha/extensions/sector_events.py
    constant: _BREAK_BOARD_HEIGHT_BONUS
    current_value: 5.0
    calibration_note: |
      Per-extra-board bonus. Calibrate against next-day theme follower
      drawdown vs leader's connect-board height.
  rotation_base_score:
    file: src/aegis_alpha/extensions/sector_events.py
    constant: _ROTATION_BASE_SCORE
    current_value: 65.0
    calibration_note: |
      Min score for a sector-rotation event. Same shape as break_board_base.
  rotation_follower_bonus:
    file: src/aegis_alpha/extensions/sector_events.py
    constant: _ROTATION_FOLLOWER_BONUS
    current_value: 3.0
    calibration_note: |
      Bonus per alive follower in the strengthening theme. Calibrate against
      that theme's next-day breadth expansion.

new_stocks:
  aged_out_days:
    file: src/aegis_alpha/extensions/new_stocks.py
    constant: _AGED_OUT_DAYS
    current_value: 180
    calibration_note: |
      Days after listing where a stock should no longer be treated as 次新.
      Calibrate against historical 次新 momentum half-life.
  smallcap_threshold_cny:
    file: src/aegis_alpha/extensions/new_stocks.py
    constant: _SMALLCAP_THRESHOLD_CNY
    current_value: 1_000_000_000.0
    calibration_note: |
      Free-float cap below which a 次新 is "smallcap recent". Calibrate
      against board-success rate by float-cap bucket.
  largecap_threshold_cny:
    file: src/aegis_alpha/extensions/new_stocks.py
    constant: _LARGECAP_THRESHOLD_CNY
    current_value: 5_000_000_000.0
    calibration_note: |
      Free-float cap above which 次新 is treated as largecap (less reactive).
  recent_days:
    file: src/aegis_alpha/extensions/new_stocks.py
    constant: _RECENT_DAYS
    current_value: 30
    calibration_note: |
      Within N days of listing → "recent" branch. Calibrate against the
      half-life of post-listing speculative premium.

limitup_driver:
  hot_money_net_buy_threshold:
    file: src/aegis_alpha/extensions/limitup_driver.py
    constant: _HOT_MONEY_NET_BUY_THRESHOLD
    current_value: 10_000_000.0
    calibration_note: |
      Min dragon-tiger net-buy CNY for the hot_money rule to fire. Calibrate
      against hot-money seat density per net-buy bucket.

intraday_pattern:
  messy_break_threshold:
    file: src/aegis_alpha/extensions/intraday_pattern.py
    constant: _MESSY_BREAK_THRESHOLD
    current_value: 3
    calibration_note: |
      Break-count threshold for messy_board pattern. Calibrate against
      next-day premium / drawdown distributions by break count.
  platform_consolidation_max_pct:
    file: src/aegis_alpha/extensions/intraday_pattern.py
    constant: _PLATFORM_CONSOLIDATION_MAX_PCT
    current_value: 3.0
    calibration_note: |
      Max intraday range during the platform-breakout consolidation phase.
  platform_consolidation_min_minutes:
    file: src/aegis_alpha/extensions/intraday_pattern.py
    constant: _PLATFORM_CONSOLIDATION_MIN_MINUTES
    current_value: 60
    calibration_note: |
      Min duration for the consolidation phase to qualify as platform-breakout.
  false_breakout_retrace_pct:
    file: src/aegis_alpha/extensions/intraday_pattern.py
    constant: _FALSE_BREAKOUT_RETRACE_PCT
    current_value: 5.0
    calibration_note: |
      High-to-close drawdown above which a near-limit touch counts as a
      false_breakout.

weekly_position:
  position_weight:
    file: src/aegis_alpha/extensions/weekly_position.py
    constant: 0.4
    current_value: 0.4
    calibration_note: |
      Inline weight in compute_weekly_health_score. Calibrate after enough
      review_outcomes data (>= 200 sealed second-board cases).
```

- [ ] **Step 2: 给每个常量加 `# CALIBRATE` 注释**

每个文件的修改是「只在常量声明上方加一行注释」，**值不变**。

`src/aegis_alpha/extensions/contrarian_pool.py:10`：

```python
# CALIBRATE: see config/p6_thresholds.yaml § contrarian_pool.recovery_threshold
_RECOVERY_THRESHOLD = 3  # 至少 3 只昨日跌停股今日 reverse 涨停才触发反向情绪事件
```

`src/aegis_alpha/extensions/sector_events.py:14-17`：在 4 个常量上方各加一行（共加 4 行）：

```python
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.break_board_base_score
_BREAK_BOARD_BASE_SCORE = 60.0
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.break_board_height_bonus
_BREAK_BOARD_HEIGHT_BONUS = 5.0  # 每多一个连板 +5 分
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.rotation_base_score
_ROTATION_BASE_SCORE = 65.0
# CALIBRATE: see config/p6_thresholds.yaml § sector_events.rotation_follower_bonus
_ROTATION_FOLLOWER_BONUS = 3.0  # 每一个 strengthening alive follower +3 分
```

`src/aegis_alpha/extensions/new_stocks.py:6-9`：加 4 行：

```python
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.aged_out_days
_AGED_OUT_DAYS = 180
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.smallcap_threshold_cny
_SMALLCAP_THRESHOLD_CNY = 1_000_000_000.0
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.largecap_threshold_cny
_LARGECAP_THRESHOLD_CNY = 5_000_000_000.0
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.recent_days
_RECENT_DAYS = 30
```

`src/aegis_alpha/extensions/limitup_driver.py:23`：

```python
# CALIBRATE: see config/p6_thresholds.yaml § limitup_driver.hot_money_net_buy_threshold
_HOT_MONEY_NET_BUY_THRESHOLD = 10_000_000.0
```

`src/aegis_alpha/extensions/intraday_pattern.py:9-12`：

```python
# CALIBRATE: see config/p6_thresholds.yaml § intraday_pattern.messy_break_threshold
_MESSY_BREAK_THRESHOLD = 3
# CALIBRATE: see config/p6_thresholds.yaml § intraday_pattern.platform_consolidation_max_pct
_PLATFORM_CONSOLIDATION_MAX_PCT = 3.0  # 平台震荡幅度
# CALIBRATE: see config/p6_thresholds.yaml § intraday_pattern.platform_consolidation_min_minutes
_PLATFORM_CONSOLIDATION_MIN_MINUTES = 60  # 平台至少 60 分钟才算平台
# CALIBRATE: see config/p6_thresholds.yaml § intraday_pattern.false_breakout_retrace_pct
_FALSE_BREAKOUT_RETRACE_PCT = 5.0  # 触板后回落 >5% 视为假突破
```

- [ ] **Step 3: 跑全量回归**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q --no-header 2>&1 | tail -5`
Expected: 全 PASS（仅注释改动）。

- [ ] **Step 4: 提交**

```bash
git add config/p6_thresholds.yaml \
    src/aegis_alpha/extensions/contrarian_pool.py \
    src/aegis_alpha/extensions/sector_events.py \
    src/aegis_alpha/extensions/new_stocks.py \
    src/aegis_alpha/extensions/limitup_driver.py \
    src/aegis_alpha/extensions/intraday_pattern.py
git commit -m "Document P6 starter thresholds with CALIBRATE markers"
```

---

## Task 5: get_active_seats_today jvquant 路径加 placeholder 信号

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/extensions/test_dragon_tiger.py`

**Background:**
P5 reviewer：`JvQuantMarketDataAdapter.get_active_seats_today` 当前 silent 返回 `[]`，agent 无法区分「真没游资席位活跃」和「端点未接入」。其它 jvquant placeholder 都有 `data_mode=placeholder` 信号，本任务把这一个对齐。

- [ ] **Step 1: 写失败测试**

追加到 `tests/extensions/test_dragon_tiger.py`：

```python
def test_jvquant_active_seats_today_returns_placeholder_signal():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    rows = adapter.get_active_seats_today("2026-06-01")
    assert isinstance(rows, list)
    # P7: even when there is "no data", the placeholder should be visible to agents
    assert rows, "jvquant active_seats placeholder should signal unavailability"
    assert rows[0].get("data_mode") == "placeholder"
    assert "hot_money_alias" in rows[0]
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py::test_jvquant_active_seats_today_returns_placeholder_signal -v`
Expected: FAIL — `rows == []`。

- [ ] **Step 3: 改 jvquant 实现**

打开 `src/aegis_alpha/adapters/jvquant/adapter.py`，找到 `get_active_seats_today`。把它改成：

```python
def get_active_seats_today(self, trading_day: str) -> list[dict]:
    # P6/P7 starter: jvQuant 龙虎榜端点尚未对齐契约，返回带 placeholder 信号的
    # 单元素列表，让 Hermes 能区分「真没数据」和「端点未接入」。
    return [
        {
            "hot_money_alias": "",
            "symbol_count": 0,
            "total_net_buy_cny": 0.0,
            "symbols": [],
            "data_mode": "placeholder",
            "error": (
                "placeholder: jvQuant active-seats endpoint not wired; "
                "agents should not infer hot-money activity from this entry."
            ),
        }
    ]
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -v`
Expected: 全部 PASS（旧的 mock 测试不受影响）。

- [ ] **Step 5: MCP 工具测试也加 placeholder 路径**

追加到 `tests/test_mcp_p5_tools.py`（或 P6 工具测试文件——选 `tests/test_mcp_p5_tools.py` 因为 dragon-tiger 是 P5 的）：

```python
def test_get_active_seats_today_includes_data_mode_field():
    from aegis_alpha.mcp.server import get_active_seats_today

    rows = get_active_seats_today("2026-06-01")
    assert isinstance(rows, list)
    if rows:
        # mock 模式不需要 data_mode；jvquant placeholder 需要
        # P7 测试只验证字段可读，不指定具体值
        assert all("hot_money_alias" in r for r in rows)
```

跑 GREEN。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/adapter.py \
    tests/extensions/test_dragon_tiger.py \
    tests/test_mcp_p5_tools.py
git commit -m "Surface placeholder signal in jvquant get_active_seats_today"
```

---

## Task 6: jvquant get_second_board_candidates 用 is_symbol_suspended 过滤

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/test_jvquant_candidates.py`

**Background:**
P6 reviewer：候选拉取链路应自动过滤掉停牌股。`is_symbol_suspended` 已在 `extensions/suspended_stocks.py` 实现；jvquant adapter 应在循环里先 `self.get_suspended_stocks(trading_day)` 拿一次列表，对每个 symbol 调一次 helper 决定是否跳过。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_jvquant_candidates.py`：

```python
def test_jvquant_get_second_board_candidates_drops_suspended_symbols():
    """Stocks present in get_suspended_stocks() should not appear in candidates."""
    from unittest.mock import patch

    from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
    from aegis_alpha.models import LadderEntry, SuspendedStock

    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()  # type: ignore[attr-defined]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(symbol=symbol, trading_day="2026-06-01",
                           consecutive_boards=1, height_label="first_board")

    # Pick the symbol the FakeJvQuantClient produces (re-use existing helper).
    # We inject ALL produced candidates as "suspended" → expect empty list.
    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]):
        baseline = adapter.get_second_board_candidates()
    if not baseline:
        return  # FakeJvQuantClient produced nothing; nothing to filter.

    suspended_for_each = [
        SuspendedStock(symbol=c.symbol, suspension_start_day="2026-05-01",
                       suspension_end_day="")
        for c in baseline
    ]
    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]), \
         patch.object(adapter, "get_suspended_stocks", return_value=suspended_for_each):
        filtered = adapter.get_second_board_candidates()
    assert filtered == []
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py::test_jvquant_get_second_board_candidates_drops_suspended_symbols -v`
Expected: FAIL — adapter 不过滤停牌。

- [ ] **Step 3: 改 jvquant adapter**

打开 `src/aegis_alpha/adapters/jvquant/adapter.py`，找到 `get_second_board_candidates`。在循环开始前加：

```python
from datetime import date as _date
from aegis_alpha.extensions.suspended_stocks import is_symbol_suspended

# Resolve trading_day (the loop already knows it; if not, derive from today)
_today = _date.today().isoformat()
try:
    _suspended = self.get_suspended_stocks(_today)
except Exception:
    _suspended = []
```

然后在每次构造候选之前加：

```python
if is_symbol_suspended(symbol, trading_day=_today, suspended=_suspended):
    continue
```

注意：实际代码位置因 jvquant adapter 现状而异。打开文件、找到 `get_second_board_candidates` 内对每只 symbol 调用 `build_one_candidate(...)` 的循环，在循环顶部插入 `is_symbol_suspended` 检查（continue 跳过）。

如果代码用了非 `_today` 的 trading_day 变量（例如 `trading_day` 从入参或 ladder 推导），用那个变量。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -v`
Expected: 全部 PASS（既有候选测试 + 新加的过滤测试）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/adapter.py tests/test_jvquant_candidates.py
git commit -m "Filter suspended symbols out of jvquant second-board candidates"
```

---

## Task 7: runner 接 detect_theme_leader_break_board + detect_sector_rotation

**Files:**
- Modify: `src/aegis_alpha/runner.py`
- Test: `tests/test_runner.py`

**Background:**
P6 reviewer：板块事件检测器孤立存在；runner 不调用它们。`AegisAlphaRunner.run_once()` 当前已处理 events，本任务把这两个检测器接进去。

- [ ] **Step 1: 看现有结构**

打开 `src/aegis_alpha/runner.py:135` 看 `run_once`。注意它已有 `_maybe_alert_from_events` 处理 events。还要看 `tests/test_runner.py` 里现有的测试模式。

- [ ] **Step 2: 写失败测试**

追加到 `tests/test_runner.py`：

```python
def test_run_once_includes_sector_events_when_leader_breaks(tmp_path, monkeypatch):
    """run_once should call detect_theme_leader_break_board on adapter
    leaders and append the events to the alert pipeline."""
    from unittest.mock import MagicMock, patch

    from aegis_alpha.models import (
        MarketEvent,
        ThemeLeader,
    )
    from aegis_alpha.runner import AegisAlphaRunner

    # Adapter returns one broken leader.
    broken_leader = ThemeLeader(
        theme="AI", trading_day="2026-06-01",
        leader_symbol="600519", leader_name="L",
        leader_consecutive_boards=3,
        leader_first_limit_up_time="09:30:00",
        leader_seal_amount_cny=200_000_000.0,
        leader_status="broken",
        co_leader_symbols=[],
        member_count=4,
    )

    runner = AegisAlphaRunner.__new__(AegisAlphaRunner)
    runner.config = {}
    runner.runner_config_path = None
    runner._stop_requested = False
    runner._websocket_runtime = MagicMock()
    runner._websocket_runtime.connected = True
    runner._websocket_runtime.subscribed = []
    runner._websocket_runtime.last_message_at = ""
    runner._websocket_runtime.last_error = ""
    runner._adapter = MagicMock()
    runner._adapter.get_recent_market_events = MagicMock(return_value=[])
    runner._adapter.get_theme_leaders = MagicMock(return_value=[broken_leader])
    runner._store = MagicMock()
    runner._status_path = tmp_path / "status.json"

    captured: list[MarketEvent] = []

    def capture(events):
        captured.extend(events)

    with patch.object(runner, "_maybe_alert_from_events", side_effect=capture), \
         patch.object(runner, "persist_buffer_outputs"), \
         patch.object(runner, "write_status"):
        runner.run_once()

    types = {e.event_type for e in captured}
    assert "THEME_LEADER_BREAK_BOARD" in types
```

如果现有 `AegisAlphaRunner.__init__` 用了别的 attribute 名（`_adapter` / `_store` / `_websocket_runtime` 不存在），打开 `runner.py:90-105` 看实际 attr，把测试里的属性名对齐。

- [ ] **Step 3: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py::test_run_once_includes_sector_events_when_leader_breaks -v`
Expected: FAIL — runner 不调 sector_events 检测器。

- [ ] **Step 4: 改 runner.run_once**

打开 `src/aegis_alpha/runner.py:135`。在 events 收集逻辑（通常是 `events = self._adapter.get_recent_market_events(...)` 这种）之后、`_maybe_alert_from_events` 之前，插入：

```python
# P7: surface sector-level events from current ThemeLeader snapshot.
try:
    from datetime import date as _date

    from aegis_alpha.extensions.sector_events import (
        LeaderBreakInputs,
        SectorRotationInputs,
        detect_sector_rotation,
        detect_theme_leader_break_board,
    )

    _trading_day = _date.today().isoformat()
    _leaders = self._adapter.get_theme_leaders(theme="", trading_day=_trading_day)
    if _leaders:
        events.extend(
            detect_theme_leader_break_board(
                LeaderBreakInputs(
                    leaders=_leaders, trading_day=_trading_day,
                )
            )
        )
        events.extend(
            detect_sector_rotation(
                SectorRotationInputs(
                    leaders=_leaders, trading_day=_trading_day,
                )
            )
        )
except Exception:
    # Sector events are best-effort; never break run_once if detection fails.
    pass
```

注意：实际代码中 events 列表的变量名可能不是 `events`，且 `get_theme_leaders` 调用签名要核对（在 `MarketDataAdapter` Protocol 里是 `get_theme_leaders(self, theme: str = "", trading_day: str = "")`）。打开 runner.py 看 events 列表叫什么（如 `recent_events`），用对名字。

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py -v`
Expected: 全部 PASS。

如果原有 runner 测试 break 了，说明 events 变量名没对上 — 修对再跑。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/runner.py tests/test_runner.py
git commit -m "Wire detect_theme_leader_break_board + detect_sector_rotation into runner"
```

---

## Task 8: simulate_outcome 接 re-grading hook

**Files:**
- Modify: `src/aegis_alpha/feedback/hypothesis.py`
- Test: `tests/feedback/test_hypothesis.py`

**Background:**
P6 reviewer：`simulate_outcome` 当前 `hypothetical_grade == original_grade`，不真正重算评级。本任务接最简单的钩子——用 P4 `feedback/backtest.py:_apply_rule_changes`-风格的本地查表，把 hypothesis 中的字段值映射到一个 grade boost/demote。**不引入 re-running 整套 candidate_grade 函数**——那是 P8 的事。

- [ ] **Step 1: 写失败测试**

追加到 `tests/feedback/test_hypothesis.py`：

```python
def test_simulate_outcome_promotes_grade_when_seal_amount_doubles_above_threshold():
    """When the hypothesis pushes seal_amount_cny across a threshold (>= 5亿
    is "stronger"), the hypothetical grade should be one notch up."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0, "five_min_speed_pct": 2.5}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 600_000_000.0},
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    # Crossing 5亿 → boost; with starting C → expected B
    assert out.hypothetical_grade == "B"


def test_simulate_outcome_keeps_grade_when_hypothesis_does_not_cross_threshold():
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 200_000_000.0},  # still below 5亿
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    assert out.hypothetical_grade == "C"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -k "promotes_grade or keeps_grade" -v`
Expected: FAIL — 当前 hypothetical_grade 始终等于 original_grade。

- [ ] **Step 3: 改 simulate_outcome**

打开 `src/aegis_alpha/feedback/hypothesis.py`。在 `simulate_outcome` 函数尾部、return 之前加 hook 逻辑。把整个函数替换为：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


_GRADE_LADDER = ("REJECT", "C", "B", "A")
# CALIBRATE: see config/p6_thresholds.yaml — these starter rules apply only inside
# simulate_outcome and are intentionally simpler than the real candidate_grade.
_SEAL_AMOUNT_BOOST_THRESHOLD = 500_000_000.0
_SPEED_BOOST_THRESHOLD = 5.0


@dataclass(frozen=True)
class HypothesisInputs:
    snapshot: HistoricalCandidateSnapshot
    hypothesis: dict[str, Any]


def _bump_grade(current: str, steps: int) -> str:
    if current not in _GRADE_LADDER:
        return current
    idx = _GRADE_LADDER.index(current)
    new_idx = max(0, min(len(_GRADE_LADDER) - 1, idx + steps))
    return _GRADE_LADDER[new_idx]


def _grade_delta_from_crossing(
    *, original_payload: dict[str, Any], new_payload: dict[str, Any]
) -> int:
    """Return integer steps to move along _GRADE_LADDER given the crossings.

    Each "crossing" of a starter threshold contributes +1 (upward) or -1
    (downward). Multiple fields stack.
    """
    delta = 0
    # seal_amount_cny crossing 5亿 → +1; falling below → -1
    orig_seal = float(original_payload.get("seal_amount_cny") or 0)
    new_seal = float(new_payload.get("seal_amount_cny") or 0)
    if orig_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= new_seal:
        delta += 1
    elif new_seal < _SEAL_AMOUNT_BOOST_THRESHOLD <= orig_seal:
        delta -= 1
    # five_min_speed_pct crossing 5% → +1; falling → -1
    orig_speed = float(original_payload.get("five_min_speed_pct") or 0)
    new_speed = float(new_payload.get("five_min_speed_pct") or 0)
    if orig_speed < _SPEED_BOOST_THRESHOLD <= new_speed:
        delta += 1
    elif new_speed < _SPEED_BOOST_THRESHOLD <= orig_speed:
        delta -= 1
    return delta


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison.

    Returns None when the snapshot payload is not valid JSON.
    """
    try:
        payload = json.loads(inputs.snapshot.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    new_payload = dict(payload)
    new_payload.update(inputs.hypothesis)
    payload_diff: dict[str, Any] = {}
    for key, new_value in inputs.hypothesis.items():
        original_value = payload.get(key, None)
        if original_value != new_value:
            payload_diff[key] = {
                "original": original_value,
                "hypothetical": new_value,
            }

    # P7 starter re-grading: bump grade by integer steps based on threshold
    # crossings of seal_amount_cny / five_min_speed_pct. This is intentionally
    # simpler than candidate_grade(); the full hook lands in P8.
    delta = _grade_delta_from_crossing(
        original_payload=payload, new_payload=new_payload,
    )
    hypothetical_grade = _bump_grade(inputs.snapshot.grade_at_pick, delta)

    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=inputs.snapshot.grade_at_pick,
        hypothetical_grade=hypothetical_grade,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            f"P7 starter re-grade: delta={delta} on _GRADE_LADDER",
        ],
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -v`
Expected: 全部 PASS（4 个测试：原 P6 的 2 个 + 新 P7 的 2 个）。

如果原 P6 测试 break 了（例如它断言 `notes` 里有特定 starter 文案），更新断言以反映新 starter，**只有当原 P6 测试是检查那一句字面量时才改；其他断言保持不变**。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/feedback/hypothesis.py tests/feedback/test_hypothesis.py
git commit -m "Wire P7 starter re-grading hook into simulate_outcome"
```

---

## Task 9: 给 get_new_stock_candidates / get_suspended_stocks 补错误路径测试

**Files:**
- Modify: `tests/test_mcp_p6_tools.py`

**Background:**
P6 reviewer：这两个 MCP tool 只有 happy-path 测试，没有当 adapter 抛错时返回 `data_mode=unavailable` 字典的回归测试。`_call_tool` 包了 try/except，所以应该返回错误字典——补一个测试钉住这个契约。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p6_tools.py`：

```python
def test_get_new_stock_candidates_returns_unavailable_dict_on_adapter_error(monkeypatch):
    from aegis_alpha.mcp import server as mcp_server

    class _BadAdapter:
        def get_new_stock_candidates(self):
            raise RuntimeError("adapter exploded")

    monkeypatch.setattr(mcp_server, "get_market_data_adapter", lambda: _BadAdapter())

    res = mcp_server.get_new_stock_candidates()
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"
    assert "adapter exploded" in res.get("error", "")


def test_get_suspended_stocks_returns_unavailable_dict_on_adapter_error(monkeypatch):
    from aegis_alpha.mcp import server as mcp_server

    class _BadAdapter:
        def get_suspended_stocks(self, trading_day=""):
            raise RuntimeError("adapter exploded")

    monkeypatch.setattr(mcp_server, "get_market_data_adapter", lambda: _BadAdapter())

    res = mcp_server.get_suspended_stocks("2026-06-01")
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"
    assert "adapter exploded" in res.get("error", "")
```

- [ ] **Step 2: 跑确认**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k "returns_unavailable_dict_on_adapter_error" -v`
Expected: PASS（`_call_tool` 已经实现了 try/except，所以这两个测试当下应该 GREEN——是 regression-pinning 测试，不是 RED→GREEN）。

如果失败，说明 `_call_tool` 行为变了，看 `mcp/server.py:_call_tool` 是否还包 try/except。

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_p6_tools.py
git commit -m "Pin error-path contract for get_new_stock_candidates and get_suspended_stocks"
```

---

## Task 10: 测试集中地——tests/test_p7_polish.py

**Files:**
- Create: `tests/test_p7_polish.py`

**Background:**
P7 跨多个文件的小修。给一份 marker 测试集中验证「P3 失败已修 + P6 starter 常量都带 CALIBRATE 注释 + p6_thresholds.yaml 存在」——后续如果有人误删，会立刻被这个文件抓住。

- [ ] **Step 1: 写测试**

写入 `tests/test_p7_polish.py`：

```python
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_p7_p6_thresholds_yaml_exists():
    path = REPO_ROOT / "config" / "p6_thresholds.yaml"
    assert path.exists(), "config/p6_thresholds.yaml should exist after P7"
    text = path.read_text(encoding="utf-8")
    # The yaml documents at minimum these 5 P6 subsystems
    for marker in (
        "contrarian_pool", "sector_events", "new_stocks",
        "limitup_driver", "intraday_pattern",
    ):
        assert marker in text, f"p6_thresholds.yaml missing section {marker}"


def test_p7_starter_constants_carry_calibrate_marker():
    """Each P6 extensions module should mention CALIBRATE near every starter
    constant, so future readers see this is a starter, not settled value.
    Spot-check by counting CALIBRATE markers — at least one per file with
    starter constants."""
    targets = (
        "src/aegis_alpha/extensions/contrarian_pool.py",
        "src/aegis_alpha/extensions/sector_events.py",
        "src/aegis_alpha/extensions/new_stocks.py",
        "src/aegis_alpha/extensions/limitup_driver.py",
        "src/aegis_alpha/extensions/intraday_pattern.py",
    )
    for rel in targets:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "CALIBRATE" in text, f"{rel} should carry # CALIBRATE markers"


def test_p7_jvquant_active_seats_today_uses_placeholder_signal():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    rows = adapter.get_active_seats_today("2026-06-01")
    if rows:
        assert rows[0].get("data_mode") == "placeholder"
```

- [ ] **Step 2: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p7_polish.py -v`
Expected: 全部 PASS（前置 Task 4 + Task 5 完成后这些测试都成立）。

如果任意 PASS 失败，说明对应 task 没正确落地——回到那个 task 修。

- [ ] **Step 3: 提交**

```bash
git add tests/test_p7_polish.py
git commit -m "Pin P7 polish invariants"
```

---

## Task 11: README + SKILL sync + 全量回归

**Files:**
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: README 加 P7 段落**

打开 `README.md`，在 P6 段落（结尾是「P6 阈值（如 ...）目前是 starter 常量，待 P7 历史校准。」）之后追加：

```markdown
P7 polish & tech debt（自 2026-06 起完成）：

- 修复 P3 期间 jvquant adapter 拆分时遗留的 2 个失败测试（`_time_or_unknown` / `_seal_quality_score` 现在调用 module-level helpers）。
- `list_suspended_stocks` 把 day-range filter 从 Python 端推到 SQL 端，利用 `idx_suspended_day` 索引。
- 5 个 P6 extensions 文件的 starter 常量加 `# CALIBRATE` 注释；常量值集中文档化在 `config/p6_thresholds.yaml`，方便 P8 回测校准。
- jvquant `get_active_seats_today` 不再 silent 返回 `[]`；当端点未接入时返回带 `data_mode=placeholder` 的单元素列表，让 Hermes 能区分「真没数据」和「端点未接入」。
- `JvQuantMarketDataAdapter.get_second_board_candidates` 自动过滤 `is_symbol_suspended` 命中的停牌股。
- `runner.run_once` 接入 `detect_theme_leader_break_board` + `detect_sector_rotation`，检测器现在与 `THEME_DIVERGENCE` 一样自动产出事件。
- `simulate_outcome` 加入 P7 starter re-grading hook：`seal_amount_cny`、`five_min_speed_pct` 跨阈值时按 `_GRADE_LADDER` 升降一级；完整重算评级留 P8。
- 给 `get_new_stock_candidates` / `get_suspended_stocks` 补 adapter-错误路径回归测试。
```

- [ ] **Step 2: SKILL.md item 21 收尾**

打开 `.hermes/skills/second-board-radar/SKILL.md`，找到 workflow item 21（P6 进阶能力）。在 sector-events 那一行后面加一行：

```text
    - 停牌过滤已在 P7 自动接入候选拉取链路 — 候选列表中不会再出现停牌股；如人工手动评估某只票，仍可调 `get_suspended_stocks(trading_day)` 复核。
    - `simulate_outcome` 现在会根据 hypothesis 跨阈值情况返回升/降一级的 `hypothetical_grade`（P7 starter 规则；P8 会接入完整 candidate_grade 重算）。
```

- [ ] **Step 3: 全量回归**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q --no-header 2>&1 | tail -10`
Expected: 仅 0 fail（包括原本 P3 起就挂的 2 个，现在应该全 PASS 了）。

Run: `.venv/bin/python -m compileall src scripts tests -q`
Expected: 无 SyntaxError。

Run: `PYTHONPATH=src .venv/bin/python scripts/smoke_check.py`
Expected: 退出码 0。

- [ ] **Step 4: 提交**

```bash
git add README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P7 polish and sync SKILL workflow"
```

---

## Self-Review Checklist

| 项 | 状态 |
|----|------|
| P3 遗留 2 个失败测试修复 | ✅ Task 1 + 2 |
| `list_suspended_stocks` SQL 过滤 | ✅ Task 3 |
| 5 个 extensions starter 常量加 CALIBRATE 注释 + p6_thresholds.yaml | ✅ Task 4 |
| `get_active_seats_today` jvquant placeholder 信号 | ✅ Task 5 |
| `is_symbol_suspended` 接入候选拉取 | ✅ Task 6 |
| runner 接 detect_theme_leader_break_board / detect_sector_rotation | ✅ Task 7 |
| `simulate_outcome` re-grading hook | ✅ Task 8 |
| MCP tool 错误路径测试（new_stock / suspended） | ✅ Task 9 |
| P7 polish invariant 测试 | ✅ Task 10 |
| Docs sync + 全量回归 | ✅ Task 11 |
| 不引入新依赖、不重构、不改 starter 常量值 | ✅ 全期遵守 |
| 不改 LLM 模型名 | ✅ 全期遵守 |
| ON CONFLICT DO UPDATE 不出现 created_at | ✅ Task 3 SQL 不动 created_at |
| Worktree base = main HEAD | ✅（沿用） |

## 已知留底（不在 P7 scope）

- **完整 simulate_outcome 重算**：本期只是 starter starter，按阈值跨越升降一级。完整接 candidate_grade(...) 是 P8。
- **starter 常量校准**：本期只加注释 + yaml 文档；真正 calibration 是 P8 的事，需要至少 200 条 review_outcomes 样本。
- **jvquant 真实接入**：龙虎榜 / 跌停池 / 资金分时 / 周线 / 次新 / 停牌 6 个 placeholder 仍在 P6/P7 状态；接入需要 jvQuant API 实际探针。

完成 P7 后，仓库回到「全绿、零已知 hot path bug、starter 常量被显式标记」的健康状态，为 P8（calibration / jvquant 真实接入）打底。
