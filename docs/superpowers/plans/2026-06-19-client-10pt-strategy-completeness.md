# client_10pt 策略落地完整度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 client_10pt 10 点二板策略每条都可被 agent 逐条走查——真值用真值、代理明标代理、缺失显式标注,零采购。

**Architecture:** 三波推进。第 1 波清配置债(#2 MA5 一致性 / #9 监控窗口文档对齐)。第 2 波加两个独立 facts-only adapter(#8 全市场板块宽度走 AkShare THS / #3+#10 合规新闻走巨潮+Tushare)。第 3 波固化已实现的买点链(#7)+ 新增 tick-rule 资金确认代理(#6,三重诚实标注)。所有新数据源失败降级,绝不拖垮主链。

**Tech Stack:** Python 3.11+、pydantic、pytest、FastMCP(`@mcp.tool`)、AkShare、Tushare(可选)、YAML 配置。

**关键现状(已核实,影响任务粒度):**
- `measurements/buypoint_state_machine.py` 三段式状态机**已完整实现**(过前高→回踩缩量→重新上冲→buy_point_alert,含 abort 守卫)。#7 = 审计 + 固化测试,非重写。
- `config/runner.yaml` + `runner.py:DEFAULT_MONITOR_WINDOWS` **已固化** 09:30–09:50 / 11:10–11:30。#9 = SKILL 文档对齐,非改代码。
- jvQuant lv2 逐笔 payload 经 `raw_lv2_large_trade_records` 解析为 `{symbol,time,trade_id,price,volume}`——**无方向字段**(已被官方文档证实)。#6 tick-rule 从 `price` 序列推断方向。
- 测试基线:`581 passed, 9 skipped`。每波完成不得回归。

---

## File Structure

**第 1 波:**
- Modify: `config/strategy_priors/client_10pt.yaml` — 删 MA5 threshold 块
- Modify: `tests/test_strategy_priors.py` — 反转 MA5 断言
- Modify: `.hermes/skills/second-board-radar/SKILL.md` — 监控窗口默认值文档对齐

**第 2 波:**
- Create: `src/aegis_alpha/adapters/sector_breadth/__init__.py`
- Create: `src/aegis_alpha/adapters/sector_breadth/breadth.py` — 板块宽度纯计算(facts-only)
- Create: `src/aegis_alpha/adapters/sector_breadth/akshare_source.py` — AkShare 取数(可失败降级)
- Create: `tests/adapters/test_sector_breadth.py`
- Create: `src/aegis_alpha/adapters/news_alignment/__init__.py`
- Create: `src/aegis_alpha/adapters/news_alignment/alignment.py` — 新闻对齐纯计算
- Create: `src/aegis_alpha/adapters/news_alignment/cninfo_source.py` — 巨潮公告取数(可失败降级)
- Create: `tests/adapters/test_news_alignment.py`
- Modify: `src/aegis_alpha/mcp/server.py` — 注册 3 个新 MCP 工具

**第 3 波:**
- Create: `src/aegis_alpha/measurements/tick_rule_orderflow.py` — tick-rule 方向推断 + 大单买入占比代理
- Create: `tests/measurements/test_tick_rule_orderflow.py`
- Create: `tests/measurements/test_buypoint_three_stage.py` — #7 三段式固化测试
- Modify: `src/aegis_alpha/mcp/server.py` — 注册 tick-rule 代理工具

---

## 第 1 波:配置债清理

### Task 1: 从 client_10pt.yaml 移除 MA5 threshold

**Files:**
- Modify: `config/strategy_priors/client_10pt.yaml:12-16`
- Test: `tests/test_strategy_priors.py:125-133`

- [ ] **Step 1: 改写 MA5 测试为"不在 thresholds"断言**

替换 `tests/test_strategy_priors.py` 的 `test_thresholds_ma5_slope`(125-133 行):

```python
    def test_ma5_slope_removed_from_active_strategy(self) -> None:
        """MA5 slope 已从 client_10pt 策略层移除(数据层字段仍保留,见 client_facts)。"""
        prior = load_active_strategy_prior()
        assert prior is not None
        names = [t.name for t in prior.thresholds]
        assert "ma5_slope_degrees" not in names
        assert "avg_turnover_10d" in names
```

同时改 `test_philosophy_guard_no_forbidden_fields`(65-83 行)里构造用的 threshold name,把 `"ma5_slope_degrees"` 换成 `"avg_turnover_10d"`、`ideal_low=5_000_000_000.0`、`ideal_high=None`、`unit="cny"`(该测试只验证无禁止字段,与具体 threshold 无关,改名避免暗示 MA5 仍是策略项)。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_strategy_priors.py::TestLoadStrategyPriors::test_ma5_slope_removed_from_active_strategy -v`
Expected: FAIL — 当前 YAML 仍含 ma5_slope_degrees,断言 `not in` 失败

- [ ] **Step 3: 从 YAML 删除 MA5 threshold 块**

`config/strategy_priors/client_10pt.yaml` 删除 12-16 行整块:

```yaml
  - name: ma5_slope_degrees
    ideal_low: 30
    ideal_high: 60
    unit: degrees
    rationale: 5日均线斜率30–60度，趋势向上但不过热。
```

删除后 `thresholds:` 下只剩 `avg_turnover_10d` 一项。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_strategy_priors.py -v`
Expected: PASS(全部)

- [ ] **Step 5: Commit**

```bash
git add config/strategy_priors/client_10pt.yaml tests/test_strategy_priors.py
git commit -m "fix(#2): 从 client_10pt 策略层移除 MA5 斜率阈值 (数据层字段保留)"
```

### Task 2: 全套测试回归确认 MA5 数据层字段仍在

**Files:**
- Test: `tests/measurements/test_client_facts.py`、`tests/test_candidate_client_facts.py`

- [ ] **Step 1: 运行 MA5 数据层相关测试**

Run: `pytest tests/measurements/test_client_facts.py tests/test_candidate_client_facts.py tests/test_candidate_assembly_facts.py -v`
Expected: PASS —— `ma5_slope_degrees` 函数与 candidate 字段未被删,这些测试应继续通过

- [ ] **Step 2: 全套回归**

Run: `pytest -q`
Expected: 与基线一致(581 passed 附近,允许因 Task 1 改名 ±0),无新增 FAIL

- [ ] **Step 3: 无改动则跳过 commit(此为验证任务)**

### Task 3: SKILL 监控窗口文档对齐(#9)

**Files:**
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: 在 SKILL 的 replay/live 工具说明处写明默认窗口**

在 SKILL.md 第 256 行附近(guidance_notes 提及监控时段处)和 `run_historical_strategy_replay` 工具说明(120 行附近)补一句:

```text
监控窗口默认值已固化在 config/runner.yaml 与 runner DEFAULT_MONITOR_WINDOWS:
open_drive 09:30–09:50、late_morning 11:10–11:30(策略第6点)。replay/live 工具
未显式传 window_start/window_end 时,应使用这两个窗口。
```

- [ ] **Step 2: 提交文档对齐**

```bash
git add .hermes/skills/second-board-radar/SKILL.md
git commit -m "docs(#9): SKILL 对齐已固化的策略监控窗口 09:30-09:50 / 11:10-11:30"
```

---

## 第 2 波:新数据源接入

### Task 4: 板块宽度纯计算函数(facts-only)

**Files:**
- Create: `src/aegis_alpha/adapters/sector_breadth/__init__.py`
- Create: `src/aegis_alpha/adapters/sector_breadth/breadth.py`
- Test: `tests/adapters/test_sector_breadth.py`

- [ ] **Step 1: 写失败测试**

Create `tests/adapters/test_sector_breadth.py`:

```python
from __future__ import annotations

from aegis_alpha.adapters.sector_breadth.breadth import compute_sector_breadth


def test_breadth_counts_limitups_within_members():
    members = ["000001", "000002", "000003", "000004"]
    limitups = {"000001", "000003", "999999"}  # 999999 不在成分内,不计
    result = compute_sector_breadth(
        theme="AI算力", members=members, limitup_symbols=limitups,
        concept_system="ths", data_source="akshare",
    )
    assert result["theme"] == "AI算力"
    assert result["member_count"] == 4
    assert result["limitup_count"] == 2
    assert result["limitup_ratio"] == 0.5
    assert result["concept_system"] == "ths"
    assert result["data_source"] == "akshare"


def test_breadth_empty_members_is_unavailable():
    result = compute_sector_breadth(
        theme="x", members=[], limitup_symbols=set(),
        concept_system="ths", data_source="akshare",
    )
    assert result["data_mode"] == "unavailable"
    assert result["member_count"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/adapters/test_sector_breadth.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现纯计算 + 包 init**

Create `src/aegis_alpha/adapters/sector_breadth/__init__.py`:

```python
from aegis_alpha.adapters.sector_breadth.breadth import compute_sector_breadth

__all__ = ["compute_sector_breadth"]
```

Create `src/aegis_alpha/adapters/sector_breadth/breadth.py`:

```python
from __future__ import annotations

from typing import Any


def compute_sector_breadth(
    *,
    theme: str,
    members: list[str],
    limitup_symbols: set[str],
    concept_system: str = "ths",
    data_source: str = "akshare",
) -> dict[str, Any]:
    """全市场板块宽度的纯计算(facts-only,无 I/O)。

    limitup_count = 成分股 ∩ 当日涨停池。非成分股的涨停不计入。
    """
    if not members:
        return {
            "theme": theme,
            "data_mode": "unavailable",
            "member_count": 0,
            "limitup_count": 0,
            "limitup_ratio": 0.0,
            "concept_system": concept_system,
            "data_source": data_source,
            "notes": ["成分股列表为空,无法计算板块宽度。"],
        }
    member_set = {str(m).strip().upper().split(".", 1)[0] for m in members}
    hit = {str(s).strip().upper().split(".", 1)[0] for s in limitup_symbols} & member_set
    limitup_count = len(hit)
    return {
        "theme": theme,
        "data_mode": "computed",
        "member_count": len(member_set),
        "limitup_count": limitup_count,
        "limitup_ratio": round(limitup_count / len(member_set), 6),
        "concept_system": concept_system,
        "data_source": data_source,
        "limitup_members": sorted(hit),
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/adapters/test_sector_breadth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/adapters/sector_breadth/ tests/adapters/test_sector_breadth.py
git commit -m "feat(#8): 板块宽度纯计算函数 (facts-only, 成分股×涨停池 join)"
```

### Task 5: 两周持续性纯计算

**Files:**
- Modify: `src/aegis_alpha/adapters/sector_breadth/breadth.py`
- Test: `tests/adapters/test_sector_breadth.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/adapters/test_sector_breadth.py` 追加:

```python
from aegis_alpha.adapters.sector_breadth.breadth import compute_breadth_continuity


def test_continuity_labels_persistent():
    # 10 个交易日,7 天有涨停 → persistent
    daily_counts = [2, 0, 3, 1, 0, 2, 4, 0, 1, 2]
    result = compute_breadth_continuity(theme="AI算力", daily_limitup_counts=daily_counts)
    assert result["active_days"] == 7
    assert result["total_limitups"] == 15
    assert result["max_daily"] == 4
    assert result["continuity_label"] == "persistent"


def test_continuity_label_fading():
    daily_counts = [5, 4, 3, 0, 0, 0, 0, 0, 0, 0]
    result = compute_breadth_continuity(theme="x", daily_limitup_counts=daily_counts)
    assert result["continuity_label"] == "fading"


def test_continuity_empty_is_unavailable():
    result = compute_breadth_continuity(theme="x", daily_limitup_counts=[])
    assert result["data_mode"] == "unavailable"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/adapters/test_sector_breadth.py::test_continuity_labels_persistent -v`
Expected: FAIL — `compute_breadth_continuity` 未定义

- [ ] **Step 3: 实现持续性计算**

在 `breadth.py` 追加:

```python
def compute_breadth_continuity(
    *,
    theme: str,
    daily_limitup_counts: list[int],
) -> dict[str, Any]:
    """两周(默认 ~10-14 交易日)板块持续性,facts-only。

    label 规则(描述性,非评分):
      - 无数据                          → unavailable
      - active_days >= 6 且后半段仍活跃 → persistent
      - 仅前半段活跃、后半段归零        → fading
      - active_days 1-2                 → emerging
      - 其余                            → weak
    """
    if not daily_limitup_counts:
        return {"theme": theme, "data_mode": "unavailable",
                "active_days": 0, "total_limitups": 0, "max_daily": 0,
                "continuity_label": "unavailable"}
    counts = [int(c) for c in daily_limitup_counts]
    active_days = sum(1 for c in counts if c > 0)
    total = sum(counts)
    max_daily = max(counts)
    half = len(counts) // 2 or 1
    first_half_active = any(c > 0 for c in counts[:half])
    second_half_active = any(c > 0 for c in counts[half:])
    if active_days >= 6 and second_half_active:
        label = "persistent"
    elif first_half_active and not second_half_active:
        label = "fading"
    elif active_days <= 2:
        label = "emerging"
    else:
        label = "weak"
    return {
        "theme": theme,
        "data_mode": "computed",
        "active_days": active_days,
        "total_limitups": total,
        "max_daily": max_daily,
        "recent_counts": counts[-5:],
        "continuity_label": label,
    }
```

在 `__init__.py` 的 import 与 `__all__` 追加 `compute_breadth_continuity`。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/adapters/test_sector_breadth.py -v`
Expected: PASS(全部)

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/adapters/sector_breadth/ tests/adapters/test_sector_breadth.py
git commit -m "feat(#8): 板块两周持续性纯计算 (persistent/fading/emerging/weak label)"
```

### Task 6: AkShare 取数层(可失败降级)

**Files:**
- Create: `src/aegis_alpha/adapters/sector_breadth/akshare_source.py`
- Test: `tests/adapters/test_sector_breadth.py`

- [ ] **Step 1: 追加失败降级测试(不真连 AkShare,用 monkeypatch)**

在 `tests/adapters/test_sector_breadth.py` 追加:

```python
from aegis_alpha.adapters.sector_breadth import akshare_source


def test_fetch_members_degrades_when_akshare_missing(monkeypatch):
    # 模拟 akshare 不可用 / 抛错 → 返回降级结构,不抛异常
    def boom(*_a, **_k):
        raise RuntimeError("akshare unavailable")
    monkeypatch.setattr(akshare_source, "_load_concept_members_raw", boom)
    result = akshare_source.fetch_theme_members("AI算力")
    assert result["data_mode"] == "unavailable"
    assert result["members"] == []
    assert "akshare" in result["data_source"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/adapters/test_sector_breadth.py::test_fetch_members_degrades_when_akshare_missing -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现取数层 + 降级**

Create `src/aegis_alpha/adapters/sector_breadth/akshare_source.py`:

```python
from __future__ import annotations

from typing import Any


def _load_concept_members_raw(theme: str) -> list[str]:
    """真实 AkShare 调用(THS 概念成分)。隔离成独立函数以便测试 monkeypatch。

    限速:调用方应在批量遍历多板块时自行 sleep,避免 429。
    """
    import akshare as ak  # lazy import — 缺失不影响其余模块
    df = ak.stock_board_concept_cons_ths(symbol=theme)
    col = "代码" if "代码" in df.columns else df.columns[0]
    return [str(v) for v in df[col].tolist()]


def fetch_theme_members(theme: str) -> dict[str, Any]:
    """取某 THS 概念的成分股列表。任何失败都降级为 unavailable,绝不抛。"""
    try:
        members = _load_concept_members_raw(theme)
    except Exception as exc:  # noqa: BLE001 — advisory source, never crash caller
        return {
            "theme": theme,
            "data_mode": "unavailable",
            "members": [],
            "data_source": "akshare.ths",
            "error": str(exc)[:200],
        }
    return {
        "theme": theme,
        "data_mode": "ok" if members else "unavailable",
        "members": members,
        "data_source": "akshare.ths",
        "concept_system": "ths",
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/adapters/test_sector_breadth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/adapters/sector_breadth/akshare_source.py tests/adapters/test_sector_breadth.py
git commit -m "feat(#8): AkShare THS 成分股取数层 (失败降级, lazy import)"
```

### Task 7: 新闻对齐纯计算(关键词匹配)

**Files:**
- Create: `src/aegis_alpha/adapters/news_alignment/__init__.py`
- Create: `src/aegis_alpha/adapters/news_alignment/alignment.py`
- Test: `tests/adapters/test_news_alignment.py`

- [ ] **Step 1: 写失败测试**

Create `tests/adapters/test_news_alignment.py`:

```python
from __future__ import annotations

from aegis_alpha.adapters.news_alignment.alignment import compute_news_alignment


def test_alignment_matches_keyword():
    docs = [
        {"title": "国家发改委发布算力基础设施新政", "date": "2026-06-18"},
        {"title": "某公司中标数据中心项目", "date": "2026-06-17"},
        {"title": "无关公告", "date": "2026-06-16"},
    ]
    result = compute_news_alignment(query="算力", docs=docs)
    assert result["matched_count"] == 1
    assert result["alignment_strength"] in {"weak", "medium"}
    assert result["source_is_caixin"] is False


def test_alignment_none_when_no_match():
    result = compute_news_alignment(query="低空经济", docs=[{"title": "算力新政", "date": "2026-06-18"}])
    assert result["matched_count"] == 0
    assert result["alignment_strength"] == "none"


def test_alignment_empty_docs_unavailable():
    result = compute_news_alignment(query="x", docs=[])
    assert result["data_mode"] == "unavailable"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/adapters/test_news_alignment.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现纯计算 + 包 init**

Create `src/aegis_alpha/adapters/news_alignment/__init__.py`:

```python
from aegis_alpha.adapters.news_alignment.alignment import compute_news_alignment

__all__ = ["compute_news_alignment"]
```

Create `src/aegis_alpha/adapters/news_alignment/alignment.py`:

```python
from __future__ import annotations

from typing import Any


def compute_news_alignment(
    *,
    query: str,
    docs: list[dict[str, Any]],
    source: str = "cninfo",
) -> dict[str, Any]:
    """题材/个股的合规新闻对齐(facts-only,关键词匹配)。

    docs: 已取回的公告/新闻列表,每条至少含 'title'。
    这是合规替代(巨潮公告/Tushare 新闻),NOT 财联社电报。
    """
    if not docs:
        return {
            "query": query, "data_mode": "unavailable",
            "matched_count": 0, "alignment_strength": "none",
            "source": source, "source_is_caixin": False,
            "notes": ["无可用公告/新闻,无法做题材对齐。"],
        }
    q = query.strip()
    matched = [d for d in docs if q and q in str(d.get("title", ""))]
    n = len(matched)
    if n == 0:
        strength = "none"
    elif n <= 2:
        strength = "weak"
    else:
        strength = "medium"
    return {
        "query": query,
        "data_mode": "computed",
        "matched_count": n,
        "alignment_strength": strength,
        "source": source,
        "source_is_caixin": False,
        "matched_titles": [str(d.get("title", "")) for d in matched[:10]],
        "notes": ["合规替代:巨潮公告/Tushare 新闻,非财联社电报原文。"],
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/adapters/test_news_alignment.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/adapters/news_alignment/ tests/adapters/test_news_alignment.py
git commit -m "feat(#3/#10): 新闻对齐纯计算 (合规替代, 明标非财联社)"
```

### Task 8: 巨潮公告取数层(可失败降级)

**Files:**
- Create: `src/aegis_alpha/adapters/news_alignment/cninfo_source.py`
- Test: `tests/adapters/test_news_alignment.py`

- [ ] **Step 1: 追加失败降级测试**

在 `tests/adapters/test_news_alignment.py` 追加:

```python
from aegis_alpha.adapters.news_alignment import cninfo_source


def test_fetch_docs_degrades_on_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("cninfo down")
    monkeypatch.setattr(cninfo_source, "_load_announcements_raw", boom)
    result = cninfo_source.fetch_recent_docs("算力", lookback_days=5)
    assert result["data_mode"] == "unavailable"
    assert result["docs"] == []
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/adapters/test_news_alignment.py::test_fetch_docs_degrades_on_error -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现取数层 + 降级**

Create `src/aegis_alpha/adapters/news_alignment/cninfo_source.py`:

```python
from __future__ import annotations

from typing import Any


def _load_announcements_raw(query: str, lookback_days: int) -> list[dict[str, Any]]:
    """真实巨潮资讯取数(通过 akshare 封装的公开公告接口)。隔离以便测试。"""
    import akshare as ak  # lazy import
    df = ak.stock_notice_report(symbol="全部")
    docs: list[dict[str, Any]] = []
    title_col = "公告标题" if "公告标题" in df.columns else df.columns[0]
    date_col = "公告日期" if "公告日期" in df.columns else df.columns[-1]
    for _, row in df.iterrows():
        docs.append({"title": str(row[title_col]), "date": str(row[date_col])})
    return docs


def fetch_recent_docs(query: str, *, lookback_days: int = 7) -> dict[str, Any]:
    """取近 N 日公告(巨潮,免费合规)。失败降级,绝不抛。"""
    try:
        docs = _load_announcements_raw(query, lookback_days)
    except Exception as exc:  # noqa: BLE001 — advisory source
        return {"query": query, "data_mode": "unavailable", "docs": [],
                "source": "cninfo", "error": str(exc)[:200]}
    return {"query": query, "data_mode": "ok" if docs else "unavailable",
            "docs": docs, "source": "cninfo"}
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/adapters/test_news_alignment.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/adapters/news_alignment/cninfo_source.py tests/adapters/test_news_alignment.py
git commit -m "feat(#3/#10): 巨潮公告取数层 (免费合规, 失败降级)"
```

### Task 9: 注册第 2 波 MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`(文件末尾 `@mcp.tool` 区)
- Test: `tests/test_mcp_sector_news_tools.py`(新建)

- [ ] **Step 1: 写 MCP 工具测试**

Create `tests/test_mcp_sector_news_tools.py`:

```python
from __future__ import annotations

from aegis_alpha.mcp import server


def test_get_market_sector_breadth_tool_exists():
    assert hasattr(server, "get_market_sector_breadth")


def test_get_sector_breadth_continuity_tool_exists():
    assert hasattr(server, "get_sector_breadth_continuity")


def test_get_news_alignment_tool_exists():
    assert hasattr(server, "get_news_alignment")


def test_news_alignment_returns_facts(monkeypatch):
    from aegis_alpha.adapters.news_alignment import cninfo_source
    monkeypatch.setattr(
        cninfo_source, "_load_announcements_raw",
        lambda *a, **k: [{"title": "算力新政发布", "date": "2026-06-18"}],
    )
    result = server.get_news_alignment("算力", lookback_days=5)
    assert result["matched_count"] == 1
    assert result["source_is_caixin"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_mcp_sector_news_tools.py -v`
Expected: FAIL — 工具未定义

- [ ] **Step 3: 在 server.py 末尾追加 3 个工具**

在 `src/aegis_alpha/mcp/server.py` 文件末尾追加:

```python
@mcp.tool
def get_market_sector_breadth(trading_day: str, theme: str) -> dict:
    """全市场板块宽度 facts(THS 体系, 成分股×涨停池 join)。失败降级 unavailable。"""
    from aegis_alpha.adapters.sector_breadth import compute_sector_breadth
    from aegis_alpha.adapters.sector_breadth.akshare_source import fetch_theme_members

    def _run(adapter):
        members_payload = fetch_theme_members(theme)
        if members_payload["data_mode"] != "ok":
            return {"theme": theme, "trading_day": trading_day,
                    "data_mode": "unavailable", "data_source": "akshare.ths",
                    "notes": ["板块成分股取数失败,无法计算宽度。"]}
        try:
            limitups = {str(item.symbol) for item in adapter.get_limitup_pool()}
        except Exception:
            limitups = set()
        result = compute_sector_breadth(
            theme=theme, members=members_payload["members"],
            limitup_symbols=limitups, concept_system="ths", data_source="akshare",
        )
        result["trading_day"] = trading_day
        return result

    return _call_tool(_run)


@mcp.tool
def get_sector_breadth_continuity(theme: str, as_of_day: str, lookback_days: int = 14) -> dict:
    """板块两周持续性 facts。当前用市场内 theme_continuity 的每日涨停计数喂入。"""
    from aegis_alpha.adapters.sector_breadth import compute_breadth_continuity

    def _run(adapter):
        continuity = adapter.get_theme_continuity(theme, as_of_day, lookback_days)
        raw = continuity if isinstance(continuity, dict) else continuity.model_dump()
        daily = raw.get("recent_daily_counts") or raw.get("recent_counts") or []
        result = compute_breadth_continuity(
            theme=theme, daily_limitup_counts=[int(x) for x in daily],
        )
        result["as_of_day"] = as_of_day
        result["lookback_days"] = lookback_days
        return result

    return _call_tool(_run)


@mcp.tool
def get_news_alignment(symbol_or_theme: str, lookback_days: int = 7) -> dict:
    """题材/个股合规新闻对齐 facts(巨潮公告)。明标非财联社电报。失败降级。"""
    from aegis_alpha.adapters.news_alignment import compute_news_alignment
    from aegis_alpha.adapters.news_alignment.cninfo_source import fetch_recent_docs

    fetched = fetch_recent_docs(symbol_or_theme, lookback_days=lookback_days)
    return compute_news_alignment(
        query=symbol_or_theme, docs=fetched.get("docs", []), source="cninfo",
    )
```

> 注:`get_sector_breadth_continuity` 依赖 adapter 的 `get_theme_continuity` 返回里含每日涨停计数字段。若该字段名不同(实现时核对 `models.py` 的 ThemeContinuity / adapter 返回),用实际字段名替换 `recent_daily_counts`/`recent_counts`;两者都没有时 `daily` 为空,函数返回 `unavailable`(已被 Task 5 的 empty 测试覆盖)。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_mcp_sector_news_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/mcp/server.py tests/test_mcp_sector_news_tools.py
git commit -m "feat(#8/#3/#10): 注册板块宽度+持续性+新闻对齐 MCP 工具"
```

---

## 第 3 波:买点固化 + tick-rule 资金代理

### Task 10: #7 三段式买点固化测试

**Files:**
- Test: `tests/measurements/test_buypoint_three_stage.py`(新建)

- [ ] **Step 1: 写端到端三段式固化测试**

Create `tests/measurements/test_buypoint_three_stage.py`:

```python
from __future__ import annotations

from aegis_alpha.measurements.buypoint_state_machine import run
from aegis_alpha.models import BuyPointThresholds, MinuteReplayBar


def _bar(time: str, price: float, volume: float) -> MinuteReplayBar:
    return MinuteReplayBar(time=time, last_price=price, volume=volume)


def test_full_three_stage_fires_buy_point_alert():
    """过前高(带量) → 回踩缩量 → 重新上冲 = buy_point_alert。"""
    prev_high = 10.0
    baseline_vol = 1000.0
    thresholds = BuyPointThresholds()
    bars = [
        _bar("09:31", 10.5, 2000.0),  # 过前高, 量比 2.0 ≥ min
        _bar("09:32", 10.1, 300.0),   # 回踩, 缩量
        _bar("09:33", 10.05, 200.0),  # 继续缩量探低
        _bar("09:34", 10.45, 900.0),  # 重新上冲接近 breakout
    ]
    ctx = run(bars, previous_high=prev_high, baseline_volume=baseline_vol, thresholds=thresholds)
    assert ctx.state == "buy_point_alert"
    assert ctx.triggered_at == "09:34"
    # 三段证据齐全
    joined = " ".join(ctx.evidence)
    assert "过前高" in joined
    assert "回踩" in joined
    assert "买入预警" in joined


def test_no_volume_breakout_stays_idle():
    """过前高但量不足 → 不进 broke_high,保持 idle。"""
    bars = [_bar("09:31", 10.5, 500.0)]  # 量比 0.5 < min
    ctx = run(bars, previous_high=10.0, baseline_volume=1000.0, thresholds=BuyPointThresholds())
    assert ctx.state == "idle"


def test_deep_drawdown_aborts():
    """回踩砸破位 → aborted。"""
    thresholds = BuyPointThresholds()
    bars = [
        _bar("09:31", 10.5, 2000.0),
        _bar("09:32", 8.0, 300.0),  # 大幅砸破位
    ]
    ctx = run(bars, previous_high=10.0, baseline_volume=1000.0, thresholds=thresholds)
    assert ctx.state == "aborted"
```

- [ ] **Step 2: 运行(预期直接 PASS,因状态机已实现)**

Run: `pytest tests/measurements/test_buypoint_three_stage.py -v`
Expected: PASS —— 若任一 FAIL,说明状态机有缺口或阈值默认值与测试不符;此时核对 `BuyPointThresholds()` 默认值(`models.py`)并调整测试的 price/volume 使其匹配真实阈值语义,而非改状态机

- [ ] **Step 3: 若 BuyPointThresholds 字段名/默认值不符则对齐测试**

核对 `grep -n "class BuyPointThresholds" -A12 src/aegis_alpha/models.py`,确认 `breakout_volume_ratio_min`、`pullback_volume_shrink_max`、`resurge_strength_min`、`pullback_max_drawdown_pct` 默认值,使 Step 1 测试数据落在正确区间。

- [ ] **Step 4: Commit**

```bash
git add tests/measurements/test_buypoint_three_stage.py
git commit -m "test(#7): 固化买点三段式端到端 (过前高→回踩缩量→重新上冲)"
```

### Task 11: tick-rule 方向推断纯函数

**Files:**
- Create: `src/aegis_alpha/measurements/tick_rule_orderflow.py`
- Test: `tests/measurements/test_tick_rule_orderflow.py`

- [ ] **Step 1: 写失败测试**

Create `tests/measurements/test_tick_rule_orderflow.py`:

```python
from __future__ import annotations

from aegis_alpha.measurements.tick_rule_orderflow import infer_tick_directions


def test_uptick_is_buy_downtick_is_sell_flat_is_neutral():
    trades = [
        {"price": 10.0, "volume": 100},   # 首笔无前价 → neutral
        {"price": 10.1, "volume": 200},   # 升 → buy
        {"price": 10.0, "volume": 150},   # 降 → sell
        {"price": 10.0, "volume": 120},   # 平 → neutral
    ]
    out = infer_tick_directions(trades)
    assert [t["side"] for t in out] == ["neutral", "buy", "sell", "neutral"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/measurements/test_tick_rule_orderflow.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: 实现 tick-rule 方向推断**

Create `src/aegis_alpha/measurements/tick_rule_orderflow.py`:

```python
from __future__ import annotations

from typing import Any


def infer_tick_directions(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用 tick-rule 从价格序列推断每笔主动方向。

    升 → buy, 降 → sell, 平/首笔 → neutral。
    这是推断代理,NOT 交易所真值 BS flag。
    """
    out: list[dict[str, Any]] = []
    prev_price: float | None = None
    for t in trades:
        price = float(t["price"])
        if prev_price is None or price == prev_price:
            side = "neutral"
        elif price > prev_price:
            side = "buy"
        else:
            side = "sell"
        out.append({**t, "side": side})
        prev_price = price
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/measurements/test_tick_rule_orderflow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/measurements/tick_rule_orderflow.py tests/measurements/test_tick_rule_orderflow.py
git commit -m "feat(#6): tick-rule 方向推断纯函数 (升=买/降=卖/平=中性)"
```

### Task 12: 大单买入占比代理 + 封板虚高警告

**Files:**
- Modify: `src/aegis_alpha/measurements/tick_rule_orderflow.py`
- Test: `tests/measurements/test_tick_rule_orderflow.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/measurements/test_tick_rule_orderflow.py` 追加:

```python
from aegis_alpha.measurements.tick_rule_orderflow import tick_rule_big_buy_ratio_proxy


def test_big_buy_ratio_proxy_basic():
    trades = [
        {"price": 10.0, "volume": 100000},   # neutral, 金额 100万
        {"price": 10.1, "volume": 100000},   # buy, 101万 ≥ 阈值
        {"price": 10.2, "volume": 100000},   # buy, 102万
        {"price": 10.1, "volume": 100000},   # sell, 101万
    ]
    result = tick_rule_big_buy_ratio_proxy(
        trades, big_trade_threshold_cny=1_000_000.0, limit_up_price=0.0,
    )
    # 大单主动买金额 / 大单主动(买+卖)金额
    assert result["is_exchange_truth"] is False
    assert result["method"] == "tick_rule"
    assert 0.0 < result["tick_rule_big_buy_ratio_proxy"] <= 1.0
    assert result["sealing_distortion_warning"] is False
    assert "accuracy_caveat" in result


def test_sealing_distortion_warning_near_limit_up():
    trades = [
        {"price": 10.99, "volume": 200000},
        {"price": 11.0, "volume": 200000},   # 触及涨停价
    ]
    result = tick_rule_big_buy_ratio_proxy(
        trades, big_trade_threshold_cny=1_000_000.0, limit_up_price=11.0,
    )
    assert result["sealing_distortion_warning"] is True


def test_empty_trades_unavailable():
    result = tick_rule_big_buy_ratio_proxy([], big_trade_threshold_cny=1_000_000.0, limit_up_price=0.0)
    assert result["data_mode"] == "unavailable"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/measurements/test_tick_rule_orderflow.py::test_big_buy_ratio_proxy_basic -v`
Expected: FAIL — `tick_rule_big_buy_ratio_proxy` 未定义

- [ ] **Step 3: 实现占比代理 + 三重诚实标注**

在 `tick_rule_orderflow.py` 追加:

```python
_CAVEAT = (
    "tick-rule 推断方向,非交易所真值 BS flag;A股实测精度约70-80%,"
    "且封板博弈时系统性虚高,不可作为主动买入真值。"
)


def tick_rule_big_buy_ratio_proxy(
    trades: list[dict[str, Any]],
    *,
    big_trade_threshold_cny: float = 1_000_000.0,
    limit_up_price: float = 0.0,
) -> dict[str, Any]:
    """大单主动买入占比代理(facts,明标非真值)。

    占比 = 大单主动买金额 / (大单主动买 + 大单主动卖)金额。
    封板虚高:当最后成交价触及/接近 limit_up_price 时置警告。
    """
    if not trades:
        return {
            "data_mode": "unavailable",
            "tick_rule_big_buy_ratio_proxy": 0.0,
            "is_exchange_truth": False,
            "method": "tick_rule",
            "accuracy_caveat": _CAVEAT,
            "sealing_distortion_warning": False,
        }
    directed = infer_tick_directions(trades)
    big_buy = 0.0
    big_sell = 0.0
    for t in directed:
        amount = float(t["price"]) * float(t["volume"])
        if amount < big_trade_threshold_cny:
            continue
        if t["side"] == "buy":
            big_buy += amount
        elif t["side"] == "sell":
            big_sell += amount
    denom = big_buy + big_sell
    ratio = round(big_buy / denom, 6) if denom > 0 else 0.0

    last_price = float(trades[-1]["price"])
    sealing = bool(limit_up_price > 0 and last_price >= limit_up_price * 0.999)

    return {
        "data_mode": "computed",
        "tick_rule_big_buy_ratio_proxy": ratio,
        "big_buy_amount_cny": round(big_buy, 2),
        "big_sell_amount_cny": round(big_sell, 2),
        "big_trade_threshold_cny": big_trade_threshold_cny,
        "is_exchange_truth": False,
        "method": "tick_rule",
        "accuracy_caveat": _CAVEAT,
        "sealing_distortion_warning": sealing,
        "notes": [
            "弱证据:买点资金确认层,主链 #5→#7 不依赖此值。",
            "封板时此代理高估主动买入,sealing_distortion_warning=true 时不可信。",
        ],
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/measurements/test_tick_rule_orderflow.py -v`
Expected: PASS(全部)

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/measurements/tick_rule_orderflow.py tests/measurements/test_tick_rule_orderflow.py
git commit -m "feat(#6): 大单买入占比 tick-rule 代理 + 封板虚高警告 (三重诚实标注)"
```

### Task 13: 注册 #6 MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Test: `tests/test_mcp_sector_news_tools.py`

- [ ] **Step 1: 追加工具存在性测试**

在 `tests/test_mcp_sector_news_tools.py` 追加:

```python
def test_get_tick_rule_orderflow_proxy_tool_exists():
    assert hasattr(server, "get_tick_rule_orderflow_proxy")
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_mcp_sector_news_tools.py::test_get_tick_rule_orderflow_proxy_tool_exists -v`
Expected: FAIL

- [ ] **Step 3: 在 server.py 末尾追加工具**

```python
@mcp.tool
def get_tick_rule_orderflow_proxy(
    symbol: str,
    window_start: str = "",
    window_end: str = "",
    big_trade_threshold_cny: float = 1_000_000.0,
    limit_up_price: float = 0.0,
) -> dict:
    """大单主动买入占比 tick-rule 代理(明标非真值,封板虚高警告)。

    与 sample_realtime_large_trade_proxy(directionless 金额)互补:
    本工具给推断方向占比,那个给无方向金额。两者都是代理,非交易所真值。
    """
    from aegis_alpha.measurements.tick_rule_orderflow import tick_rule_big_buy_ratio_proxy

    def _run(adapter):
        sample = adapter.sample_realtime_large_trade_proxy(
            symbol, window_start=window_start, window_end=window_end,
            threshold_cny=big_trade_threshold_cny,
        )
        raw = sample if isinstance(sample, dict) else sample.model_dump()
        trades = raw.get("sample_trades") or raw.get("recent_trades") or []
        result = tick_rule_big_buy_ratio_proxy(
            [{"price": float(t.get("price", 0.0)), "volume": float(t.get("volume", 0.0))} for t in trades],
            big_trade_threshold_cny=big_trade_threshold_cny,
            limit_up_price=limit_up_price,
        )
        result["symbol"] = symbol
        result["window"] = {"start": window_start, "end": window_end}
        result["upstream_sample_available"] = bool(raw.get("sample_available", False))
        return result

    return _call_tool(_run)
```

> 注:实现时核对 `sample_realtime_large_trade_proxy` 真实返回里逐笔列表的字段名(`grep -n "sample_trades\|recent_trades\|sample_available" src/aegis_alpha/adapters/jvquant/adapter.py`),用实际字段名替换。若上游样本不可用,trades 为空 → 代理返回 `data_mode=unavailable`(Task 12 已覆盖)。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_mcp_sector_news_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/mcp/server.py tests/test_mcp_sector_news_tools.py
git commit -m "feat(#6): 注册 tick-rule 大单买入占比代理 MCP 工具"
```

### Task 14: SKILL 文档收尾 + 全套回归

**Files:**
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: 在 SKILL 工具清单与说明补新工具**

在 SKILL.md 的 "Required MCP Tools" 列表追加 `get_market_sector_breadth`、`get_sector_breadth_continuity`、`get_news_alignment`、`get_tick_rule_orderflow_proxy`,并各补一段说明,重点写明:
- `get_market_sector_breadth` / `get_sector_breadth_continuity`:全市场 THS 体系板块宽度,升级 packet-local 代理;明标 concept_system=ths、可能 unavailable。
- `get_news_alignment`:合规替代(巨潮公告),**非财联社电报**;弱证据辅助题材持续性。
- `get_tick_rule_orderflow_proxy`:**非真值**大单买入占比代理,封板时 `sealing_distortion_warning=true` 不可信;只作买点资金确认弱证据,主链不依赖。

- [ ] **Step 2: 全套回归**

Run: `pytest -q`
Expected: 基线(581)+ 新增测试全部 PASS,无回归

- [ ] **Step 3: Commit**

```bash
git add .hermes/skills/second-board-radar/SKILL.md
git commit -m "docs: SKILL 收录板块宽度/新闻对齐/tick-rule 代理工具 (诚实标注)"
```

---

## Self-Review

**Spec coverage:**
- #2 MA5 一致性 → Task 1-2 ✓
- #9 监控窗口 → Task 3(已固化,文档对齐)✓
- #8 板块宽度 → Task 4-6, 9 ✓
- #3/#10 新闻对齐 → Task 7-8, 9 ✓
- #7 买点固化 → Task 10 ✓
- #6 tick-rule 代理 → Task 11-13 ✓
- SKILL 收尾 → Task 3, 14 ✓

**Placeholder scan:** 每个 code step 含完整代码;两处"实现时核对字段名"(Task 9 持续性字段、Task 13 逐笔字段)已给出 grep 命令 + 降级兜底(空→unavailable,已被测试覆盖),非占位符而是明确的核对指令。

**Type consistency:**
- `compute_sector_breadth` / `compute_breadth_continuity`(Task 4/5)→ Task 9 调用一致
- `fetch_theme_members` 返回 `data_mode in {ok,unavailable}`(Task 6)→ Task 9 判断 `!= "ok"` 一致
- `compute_news_alignment(query, docs, source)`(Task 7)→ Task 9 调用一致
- `fetch_recent_docs(query, lookback_days)` 返回 `docs`(Task 8)→ Task 9 取 `docs` 一致
- `infer_tick_directions` 输出 `side`(Task 11)→ `tick_rule_big_buy_ratio_proxy` 消费 `side`(Task 12)一致
- `tick_rule_big_buy_ratio_proxy` 关键字参数 `big_trade_threshold_cny`/`limit_up_price`(Task 12)→ Task 13 调用一致

## 验收

三波 14 任务完成后:10 点中 8 点真值,#6/#10 诚实代理。全套测试不回归。主触发链 #5→#7 全真值实盘可跑。

二期(本计划外):#3+#4 闭环验证(零成本,优先)→ #6 Wind 真值(花钱,验证有 alpha 后再投)。
