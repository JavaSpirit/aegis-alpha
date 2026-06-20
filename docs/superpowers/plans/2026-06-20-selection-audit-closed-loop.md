# 选股审计闭环验证 Implementation Plan (二期A: #3+#4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 持久化 agent 收盘选股决策(选了谁/落选谁/相对理由/caveat),次日自动对照目标日盘中触发+次日结果,并固化反机械排序基准,回答"agent 选的票是否胜过朴素基准"。

**Architecture:** 新表 selection_audits(migration m0008)+ Pydantic 模型(facts-only)+ 纯计算模块(feedback/selection_audit.py)+ store 持久化方法 + 3 个 MCP 工具(record/get/trigger_validation)+ runner 次日自动验证钩子。复用现有 decision_packet/next_day_outcomes,零采购。

**Tech Stack:** Python 3.11+(实际 3.13)、pydantic、sqlite3、pytest、FastMCP(@mcp.tool)、YAML 配置。

**关键环境事实(已核实):**
- 测试运行器:系统 python 是 3.9 会失败,**必须用** `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest ...`。
- 工作目录:git worktree `/Users/faillonexie/Projects/aegis-alpha/.claude/worktrees/client-10pt-completeness`,branch worktree-client-10pt-completeness。
- 测试基线:`601 passed, 7 skipped`,不得回归。
- Migration 自动发现:`db_migrations.py` 按文件名正则 `^m(\d{4})_` 发现并排序,新增 `m0008_*.py` 文件即生效,无需注册。
- Store 落库模式(`storage.py:338 save_agent_review`):`INSERT INTO ...; model_dump_json()` 存 payload;读用 `model_validate_json`。
- `AlertStore.create(*, title, severity="info", body="", event_id="", symbol="", theme="")` 自带 event_id dedup(`storage.py` AlertStore)。
- runner advisory 模式(`runner.py:364 detect_buypoints_in_window`):try/except 吞异常,"runner liveness must not depend on it"。runner 有 `self.store`(AegisAlphaStore)、`self.config`。

---

## File Structure

- Create: `src/aegis_alpha/db_migrations_files/m0008_selection_audits.py` — 建表
- Modify: `src/aegis_alpha/models.py` — SelectionPick / RejectedCandidate / SelectionAudit
- Create: `src/aegis_alpha/feedback/selection_audit.py` — 纯计算(audit_id / 基准对比 / confidence)
- Modify: `src/aegis_alpha/storage.py` — save_selection_audit / get_selection_audit_by_day / count_selection_audit_days
- Modify: `src/aegis_alpha/mcp/server.py` — 3 个 MCP 工具
- Modify: `src/aegis_alpha/runner.py` — validate_selections_next_day 钩子 + run_once 调用
- Modify: `config/runner.yaml` — selection_validation 配置
- Tests: `tests/test_selection_audit_model.py`, `tests/measurements/test_selection_audit_calc.py`, `tests/test_selection_audit_store.py`, `tests/test_mcp_selection_audit_tools.py`, `tests/test_runner_selection_validation.py`

---

## Task 1: Pydantic 模型 (facts-only)

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Test: `tests/test_selection_audit_model.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_selection_audit_model.py`:

```python
from __future__ import annotations

from aegis_alpha.models import SelectionPick, RejectedCandidate, SelectionAudit

FORBIDDEN = {"grade", "score", "passed", "probability", "reject", "meets_threshold"}


def _flatten_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _flatten_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _flatten_keys(item)
    return keys


def test_build_selection_audit():
    audit = SelectionAudit(
        audit_id="a1",
        as_of_day="2026-06-19",
        picks=[SelectionPick(symbol="002491", rank=1, relative_reason="胜过高封单额的X", caveats=["盘外新闻未确认"])],
        rejected=[RejectedCandidate(symbol="300475", why_rejected="题材分歧", beat_by="002491")],
        baseline={"seal_amount": ["600000"], "seal_ratio": ["002491"], "first_seal_time": ["600000"]},
        equals_baseline=False,
        confidence_label="exploratory",
        candidate_pool_size=55,
    )
    assert audit.picks[0].symbol == "002491"
    assert audit.picks[0].rank == 1
    assert audit.rejected[0].beat_by == "002491"
    assert audit.equals_baseline is False


def test_philosophy_guard_no_forbidden_fields():
    audit = SelectionAudit(audit_id="x", as_of_day="2026-06-19")
    keys = _flatten_keys(audit.model_dump())
    assert not (FORBIDDEN & keys), f"forbidden fields: {FORBIDDEN & keys}"


def test_defaults_minimal():
    audit = SelectionAudit(audit_id="x", as_of_day="2026-06-19")
    assert audit.picks == []
    assert audit.rejected == []
    assert audit.equals_baseline is False
    assert audit.confidence_label == "exploratory"
```

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_model.py -v`
Expected: FAIL (ImportError: SelectionPick).

- [ ] **Step 3: 实现模型**

在 `src/aegis_alpha/models.py` 末尾追加(若文件已 import Field/BaseModel 则复用):

```python
class SelectionPick(BaseModel):
    symbol: str
    rank: int = 0
    relative_reason: str = ""
    caveats: list[str] = Field(default_factory=list)


class RejectedCandidate(BaseModel):
    symbol: str
    why_rejected: str = ""
    beat_by: str = ""


class SelectionAudit(BaseModel):
    audit_id: str = ""
    as_of_day: str
    picks: list[SelectionPick] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    baseline: dict[str, Any] = Field(default_factory=dict)
    equals_baseline: bool = False
    confidence_label: str = "exploratory"
    candidate_pool_size: int = 0
    provider: str = ""
    model: str = ""
    created_at: str = ""
```

确认 `models.py` 顶部已有 `from typing import Any` 和 `from pydantic import BaseModel, Field`(它有,既有模型在用)。

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_model.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py tests/test_selection_audit_model.py
git commit -m "feat(#3): SelectionAudit/Pick/Rejected 模型 (facts-only, 哲学守卫)"
```

---

## Task 2: migration m0008 建表

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0008_selection_audits.py`
- Test: `tests/test_selection_audit_store.py`(仅建表断言部分)

- [ ] **Step 1: 写建表测试**

Create `tests/test_selection_audit_store.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.storage import AegisAlphaStore


def test_selection_audits_table_exists(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))  # applies migrations on init
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='selection_audits'"
        ).fetchone()
    assert row is not None


def test_selection_audits_columns(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(selection_audits)").fetchall()}
    expected = {"audit_id", "as_of_day", "picks_json", "rejected_json", "baseline_json",
                "equals_baseline", "confidence_label", "candidate_pool_size",
                "provider", "model", "created_at"}
    assert expected <= cols
```

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_store.py -v`
Expected: FAIL (table not found).

- [ ] **Step 3: 实现 migration**

Create `src/aegis_alpha/db_migrations_files/m0008_selection_audits.py`:

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """Create selection_audits table for closed-loop strategy validation (二期A #3)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS selection_audits (
            audit_id TEXT PRIMARY KEY,
            as_of_day TEXT NOT NULL,
            picks_json TEXT NOT NULL DEFAULT '[]',
            rejected_json TEXT NOT NULL DEFAULT '[]',
            baseline_json TEXT NOT NULL DEFAULT '{}',
            equals_baseline INTEGER NOT NULL DEFAULT 0,
            confidence_label TEXT NOT NULL DEFAULT 'exploratory',
            candidate_pool_size INTEGER NOT NULL DEFAULT 0,
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_selection_audits_as_of_day
            ON selection_audits (as_of_day);
        """
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_store.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/db_migrations_files/m0008_selection_audits.py tests/test_selection_audit_store.py
git commit -m "feat(#3): migration m0008 selection_audits 表"
```

---

## Task 3: 纯计算模块 (audit_id / 基准对比 / confidence)

**Files:**
- Create: `src/aegis_alpha/feedback/selection_audit.py`
- Test: `tests/measurements/test_selection_audit_calc.py`

- [ ] **Step 1: 写失败测试**

Create `tests/measurements/test_selection_audit_calc.py`:

```python
from __future__ import annotations

from aegis_alpha.feedback.selection_audit import (
    compute_audit_id,
    compute_equals_baseline,
    compute_confidence_label,
)


def test_audit_id_idempotent():
    a = compute_audit_id("2026-06-19", ["002491", "300475"])
    b = compute_audit_id("2026-06-19", ["300475", "002491"])  # order-independent
    assert a == b
    c = compute_audit_id("2026-06-19", ["002491"])
    assert c != a


def test_equals_baseline_true_when_matches_a_baseline():
    picks = ["002491", "300475"]
    baseline = {
        "seal_amount": ["600000", "999999"],
        "seal_ratio": ["002491", "300475"],   # identical set to picks
        "first_seal_time": ["111111", "222222"],
    }
    assert compute_equals_baseline(picks, baseline) is True


def test_equals_baseline_false_when_distinct():
    picks = ["002491", "300475"]
    baseline = {
        "seal_amount": ["600000", "999999"],
        "seal_ratio": ["111111", "222222"],
        "first_seal_time": ["333333", "444444"],
    }
    assert compute_equals_baseline(picks, baseline) is False


def test_confidence_label_exploratory_below_10_days():
    assert compute_confidence_label(accumulated_days=3) == "exploratory"
    assert compute_confidence_label(accumulated_days=9) == "exploratory"


def test_confidence_label_low_or_medium_at_or_above_10():
    assert compute_confidence_label(accumulated_days=10) in {"low", "medium"}
    assert compute_confidence_label(accumulated_days=30) in {"low", "medium"}
```

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/measurements/test_selection_audit_calc.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: 实现**

Create `src/aegis_alpha/feedback/selection_audit.py`:

```python
from __future__ import annotations

import hashlib
from typing import Any


def compute_audit_id(as_of_day: str, pick_symbols: list[str]) -> str:
    """幂等哈希:同 as_of_day + 同组 picks(顺序无关)→ 同 ID。"""
    norm = "|".join(sorted(str(s).strip().upper() for s in pick_symbols))
    raw = f"{as_of_day}::{norm}"
    return "sa_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def compute_equals_baseline(pick_symbols: list[str], baseline: dict[str, Any]) -> bool:
    """agent TopN 是否与任一朴素基准 TopN 的 symbol 集合完全相同(反机械排序)。"""
    pick_set = {str(s).strip().upper() for s in pick_symbols}
    if not pick_set:
        return False
    for key in ("seal_amount", "seal_ratio", "first_seal_time"):
        base_list = baseline.get(key) or []
        base_set = {str(s).strip().upper() for s in base_list}
        if base_set and base_set == pick_set:
            return True
    return False


def compute_confidence_label(*, accumulated_days: int) -> str:
    """样本 <10 交易日强制 exploratory;>=10 给 low(默认保守)。"""
    if accumulated_days < 10:
        return "exploratory"
    return "low"
```

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/measurements/test_selection_audit_calc.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/feedback/selection_audit.py tests/measurements/test_selection_audit_calc.py
git commit -m "feat(#3): 选股审计纯计算 (幂等audit_id/基准对比/confidence守卫)"
```

---

## Task 4: store 持久化方法

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Test: `tests/test_selection_audit_store.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `tests/test_selection_audit_store.py` 追加:

```python
from aegis_alpha.models import SelectionAudit, SelectionPick


def test_save_and_get_selection_audit(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    audit = SelectionAudit(
        audit_id="sa_test1", as_of_day="2026-06-19",
        picks=[SelectionPick(symbol="002491", rank=1)],
        candidate_pool_size=55,
    )
    store.save_selection_audit(audit)
    got = store.get_selection_audit_by_day("2026-06-19")
    assert got is not None
    assert got.audit_id == "sa_test1"
    assert got.picks[0].symbol == "002491"


def test_save_selection_audit_idempotent_upsert(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    a = SelectionAudit(audit_id="sa_dup", as_of_day="2026-06-19",
                       picks=[SelectionPick(symbol="002491", rank=1)])
    store.save_selection_audit(a)
    store.save_selection_audit(a)  # same audit_id → upsert, not duplicate
    assert store.count_selection_audit_days() == 1


def test_count_selection_audit_days_distinct(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    store.save_selection_audit(SelectionAudit(audit_id="s1", as_of_day="2026-06-18"))
    store.save_selection_audit(SelectionAudit(audit_id="s2", as_of_day="2026-06-19"))
    assert store.count_selection_audit_days() == 2


def test_get_selection_audit_missing_returns_none(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    assert store.get_selection_audit_by_day("2099-01-01") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_store.py -v`
Expected: 新增 4 个 FAIL(方法未定义),前 2 个建表测试仍 PASS。

- [ ] **Step 3: 实现 store 方法**

先确认 storage.py 顶部 import 含 `SelectionAudit`。在 import 区追加:`from aegis_alpha.models import SelectionAudit`(若该行已 import 多个 model,加进去)。在 `AegisAlphaStore` 类内(`save_agent_review` 方法附近)追加:

```python
    def save_selection_audit(self, audit: "SelectionAudit") -> "SelectionAudit":
        from aegis_alpha.helpers import now_iso  # 若 storage 顶部已 import now_iso 则删此行
        if not audit.created_at:
            audit.created_at = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO selection_audits
                    (audit_id, as_of_day, picks_json, rejected_json, baseline_json,
                     equals_baseline, confidence_label, candidate_pool_size,
                     provider, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    picks_json=excluded.picks_json,
                    rejected_json=excluded.rejected_json,
                    baseline_json=excluded.baseline_json,
                    equals_baseline=excluded.equals_baseline,
                    confidence_label=excluded.confidence_label,
                    candidate_pool_size=excluded.candidate_pool_size,
                    provider=excluded.provider,
                    model=excluded.model
                """,
                (
                    audit.audit_id, audit.as_of_day,
                    _dump_list(audit.picks), _dump_list(audit.rejected),
                    __import__("json").dumps(audit.baseline, ensure_ascii=False),
                    1 if audit.equals_baseline else 0,
                    audit.confidence_label, audit.candidate_pool_size,
                    audit.provider, audit.model, audit.created_at,
                ),
            )
        return audit

    def get_selection_audit_by_day(self, as_of_day: str) -> "SelectionAudit | None":
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT audit_id, as_of_day, picks_json, rejected_json, baseline_json,
                       equals_baseline, confidence_label, candidate_pool_size,
                       provider, model, created_at
                FROM selection_audits WHERE as_of_day = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (as_of_day,),
            ).fetchone()
        if row is None:
            return None
        import json
        from aegis_alpha.models import SelectionAudit, SelectionPick, RejectedCandidate
        return SelectionAudit(
            audit_id=row[0], as_of_day=row[1],
            picks=[SelectionPick.model_validate(p) for p in json.loads(row[2] or "[]")],
            rejected=[RejectedCandidate.model_validate(r) for r in json.loads(row[3] or "[]")],
            baseline=json.loads(row[4] or "{}"),
            equals_baseline=bool(row[5]),
            confidence_label=row[6], candidate_pool_size=row[7],
            provider=row[8], model=row[9], created_at=row[10],
        )

    def count_selection_audit_days(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT as_of_day) FROM selection_audits"
            ).fetchone()
        return int(row[0]) if row else 0
```

并在 `storage.py` 文件内(模块级,类外)加一个小 helper:

```python
def _dump_list(items: list) -> str:
    import json
    return json.dumps([i.model_dump() for i in items], ensure_ascii=False)
```

> 实现注记:核对 storage.py 顶部 `now_iso` 的真实 import 路径(grep `now_iso` in storage.py)——若已模块级 import,删掉方法内那行局部 import,直接用。`_connect` 是既有方法(save_agent_review 在用)。

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_selection_audit_store.py -v`
Expected: 全部 PASS(2 建表 + 4 新增 = 6)。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/storage.py tests/test_selection_audit_store.py
git commit -m "feat(#3): selection_audit store 持久化 (幂等upsert/按日取/计数)"
```

---

## Task 5: record + get MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Test: `tests/test_mcp_selection_audit_tools.py`

- [ ] **Step 1: 写测试**

Create `tests/test_mcp_selection_audit_tools.py`:

```python
from __future__ import annotations

import json
from aegis_alpha.mcp import server


def test_record_and_get_selection_audit_roundtrip(monkeypatch, tmp_path):
    # Force a fresh store in a temp DB via the dependency the server uses.
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)

    picks = json.dumps([{"symbol": "002491", "rank": 1, "relative_reason": "胜过X", "caveats": []}])
    rec = server.record_selection_audit("2026-06-19", picks, candidate_pool_size=55)
    assert rec["as_of_day"] == "2026-06-19"
    assert rec["equals_baseline"] in (True, False)
    assert "confidence_label" in rec

    got = server.get_selection_audit("2026-06-19")
    assert got["picks"][0]["symbol"] == "002491"


def test_get_selection_audit_unavailable(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    res = server.get_selection_audit("2099-01-01")
    assert res["data_mode"] == "unavailable"


def test_record_flags_equals_baseline_warning(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    # baseline computed from candidate pool will be empty in this unit test path,
    # so equals_baseline should be False and no warning.
    picks = json.dumps([{"symbol": "002491", "rank": 1}])
    rec = server.record_selection_audit("2026-06-19", picks)
    assert rec["equals_baseline"] is False
```

> 实现注记:核对 server.py 里取 store 的真实依赖名(grep `get_store\|_call_store\|AegisAlphaStore` in server.py;`server.py:30 _call_store` 已存在)。若 server 用 `_call_store(callback)` 而非 `get_store()`,把 monkeypatch 目标和测试改为与真实依赖一致(读 server.py:30 区域确认),并让工具内部走 `_call_store`。

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_mcp_selection_audit_tools.py -v`
Expected: FAIL（工具未定义）。

- [ ] **Step 3: 实现两个工具(append 到 server.py 末尾)**

先 READ `server.py:30` 附近的 `_call_store` 与 `_call_tool`,按真实模式实现。参考结构:

```python
@mcp.tool
def record_selection_audit(
    as_of_day: str,
    picks_json: str,
    rejected_json: str = "",
    candidate_pool_size: int = 0,
    provider: str = "",
    model: str = "",
) -> dict:
    """记录 agent 收盘选股决策 (facts-only)。自动算三朴素基准对比 + confidence 守卫 + 即时反机械排序提醒。"""
    import json as _json
    from aegis_alpha.models import SelectionAudit, SelectionPick, RejectedCandidate
    from aegis_alpha.feedback.selection_audit import (
        compute_audit_id, compute_equals_baseline, compute_confidence_label,
    )

    picks_raw = _json.loads(picks_json or "[]")
    rejected_raw = _json.loads(rejected_json or "[]")
    picks = [SelectionPick.model_validate(p) for p in picks_raw]
    rejected = [RejectedCandidate.model_validate(r) for r in rejected_raw]
    pick_symbols = [p.symbol for p in picks]

    def _run(store):
        # 三朴素基准:从当天候选池事实取 TopN(封单额/封成比/首封时间)
        baseline = _build_naive_baselines(as_of_day, len(pick_symbols))
        equals = compute_equals_baseline(pick_symbols, baseline)
        accumulated = store.count_selection_audit_days()
        confidence = compute_confidence_label(accumulated_days=accumulated)
        audit = SelectionAudit(
            audit_id=compute_audit_id(as_of_day, pick_symbols),
            as_of_day=as_of_day, picks=picks, rejected=rejected,
            baseline=baseline, equals_baseline=equals,
            confidence_label=confidence, candidate_pool_size=candidate_pool_size,
            provider=provider, model=model,
        )
        store.save_selection_audit(audit)
        result = audit.model_dump()
        if equals:
            result["anti_mechanical_warning"] = (
                "你的 TopN 等同某朴素基准(封单额/封成比/首封时间),未体现额外 alpha;请重新评估或明确标注。"
            )
        return result

    return _call_store(_run)


@mcp.tool
def get_selection_audit(as_of_day: str) -> dict:
    """取某收盘日的选股审计 (facts-only)。无记录返回 unavailable。"""
    def _run(store):
        audit = store.get_selection_audit_by_day(as_of_day)
        if audit is None:
            return {"as_of_day": as_of_day, "data_mode": "unavailable",
                    "notes": ["该日无选股审计记录。"]}
        return {**audit.model_dump(), "data_mode": "ok"}

    return _call_store(_run)
```

并在 server.py 加一个内部 helper `_build_naive_baselines(as_of_day, top_n)`,从已有的候选池/历史二板事实取三基准 TopN。最小实现:复用 `get_historical_second_board_candidates(as_of_day)` 的结果,按 `seal_amount_cny` / `seal_to_turnover_ratio` / `first_seal_time` 各排序取前 top_n 的 symbol 列表;任一不可用则该基准为 []。务必 try/except 降级——基准拿不到不应让 record 失败(基准空 → equals_baseline=False)。

```python
def _build_naive_baselines(as_of_day: str, top_n: int) -> dict:
    n = max(1, int(top_n or 1))
    try:
        rows = get_historical_second_board_candidates(as_of_day, limit=50)
        items = rows if isinstance(rows, list) else rows.get("candidates", [])
    except Exception:
        return {"seal_amount": [], "seal_ratio": [], "first_seal_time": []}

    def _top(key: str, reverse: bool) -> list[str]:
        try:
            ranked = sorted(
                [i for i in items if isinstance(i, dict) and i.get(key) is not None],
                key=lambda i: i.get(key), reverse=reverse,
            )
            return [str(i.get("symbol")) for i in ranked[:n]]
        except Exception:
            return []

    return {
        "seal_amount": _top("max_seal_amount_cny", True),
        "seal_ratio": _top("seal_to_turnover_ratio", True),
        "first_seal_time": _top("final_seal_time", False),
    }
```

> 实现注记:核对 `get_historical_second_board_candidates` 真实返回项的字段名(grep 其实现);若字段名不同(如 seal_amount_cny vs max_seal_amount_cny),用实际名替换。字段缺失时 `_top` 返回 [],基准为空→equals_baseline False,record 仍成功。这是诚实降级,不是 bug。

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_mcp_selection_audit_tools.py -v`
Expected: 3 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/mcp/server.py tests/test_mcp_selection_audit_tools.py
git commit -m "feat(#3): record_selection_audit + get_selection_audit MCP 工具 (基准对比+即时提醒)"
```

---

## Task 6: trigger_validation MCP 工具 (#4 对照闭环)

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Test: `tests/test_mcp_selection_audit_tools.py`(追加)

- [ ] **Step 1: 追加测试**

```python
def test_trigger_validation_joins_audit_and_facts(monkeypatch, tmp_path):
    import json as _json
    from aegis_alpha.storage import AegisAlphaStore
    from aegis_alpha.mcp import server as srv

    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)

    # seed an audit
    picks = _json.dumps([{"symbol": "002491", "rank": 1, "relative_reason": "胜过X"}])
    srv.record_selection_audit("2026-06-18", picks)

    # stub the two upstream fact sources used by trigger validation
    monkeypatch.setattr(srv, "_validation_intraday_trigger",
                        lambda sym, as_of, target, ws, we: {"triggered": True, "trigger_time": "09:33"})
    monkeypatch.setattr(srv, "_validation_next_day_outcome",
                        lambda sym, target: {"sealed_second_board": True, "next_day_open_pct": 3.2})

    res = srv.get_selection_trigger_validation("2026-06-18", "2026-06-19")
    assert res["data_mode"] == "ok"
    assert res["total"] == 1
    assert res["per_pick"][0]["symbol"] == "002491"
    assert res["per_pick"][0]["triggered"] is True
    assert res["triggered_count"] == 1
    assert "confidence_label" in res


def test_trigger_validation_no_audit_unavailable(monkeypatch, tmp_path):
    from aegis_alpha.storage import AegisAlphaStore
    from aegis_alpha.mcp import server as srv
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    monkeypatch.setattr(srv, "get_store", lambda: store)
    res = srv.get_selection_trigger_validation("2099-01-01", "2099-01-02")
    assert res["data_mode"] == "unavailable"
```

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_mcp_selection_audit_tools.py -v`
Expected: 新增 2 FAIL。

- [ ] **Step 3: 实现**

在 server.py 追加工具 + 两个可 monkeypatch 的内部取数 helper(隔离上游,便于测试且失败降级):

```python
def _validation_intraday_trigger(symbol: str, as_of_day: str, target_day: str,
                                 window_start: str, window_end: str) -> dict:
    """从 decision packet 取该 symbol 目标日盘中触发事实。失败降级。"""
    try:
        packet = get_strategy_decision_packet(
            as_of_day, target_day, symbol, limit=1,
            window_start=window_start, window_end=window_end,
        )
        raw = packet if isinstance(packet, dict) else packet.model_dump()
        replay = (raw.get("target_day_replay") or {})
        items = replay.get("results") or replay.get("items") or []
        for it in items:
            if isinstance(it, dict) and str(it.get("symbol", "")).split(".")[0] == symbol.split(".")[0]:
                diag = it.get("pattern_diagnostics") or {}
                return {
                    "triggered": bool(it.get("state") == "buy_point_alert" or diag.get("opening_window_crossed")),
                    "trigger_time": it.get("triggered_at", ""),
                    "data_mode": "ok",
                }
        return {"triggered": False, "trigger_time": "", "data_mode": "ok"}
    except Exception:
        return {"triggered": None, "trigger_time": "", "data_mode": "unavailable"}


def _validation_next_day_outcome(symbol: str, target_day: str) -> dict:
    """取触发后次日结果。失败降级。"""
    try:
        out = get_second_board_next_day_outcomes(target_day, symbol)
        raw = out if isinstance(out, list) else out.get("outcomes", [])
        for o in raw:
            if isinstance(o, dict) and str(o.get("symbol", "")).split(".")[0] == symbol.split(".")[0]:
                return {"sealed_second_board": o.get("sealed_second_board"),
                        "next_day_open_pct": o.get("next_day_open_pct"),
                        "data_mode": "ok"}
        return {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "ok"}
    except Exception:
        return {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "unavailable"}


@mcp.tool
def get_selection_trigger_validation(
    as_of_day: str, target_day: str,
    window_start: str = "09:31", window_end: str = "10:00",
) -> dict:
    """闭环对照 (#4):收盘选的 TopN vs 目标日盘中触发 + 次日结果。只读纯组合,facts-only。"""
    def _run(store):
        audit = store.get_selection_audit_by_day(as_of_day)
        if audit is None:
            return {"as_of_day": as_of_day, "target_day": target_day,
                    "data_mode": "unavailable", "notes": ["该日无选股审计,无法对照。"]}
        per_pick = []
        triggered = 0
        for pick in audit.picks:
            trig = _validation_intraday_trigger(pick.symbol, as_of_day, target_day, window_start, window_end)
            outcome = _validation_next_day_outcome(pick.symbol, target_day)
            if trig.get("triggered") is True:
                triggered += 1
            per_pick.append({
                "symbol": pick.symbol, "rank": pick.rank,
                "relative_reason": pick.relative_reason,
                "triggered": trig.get("triggered"),
                "trigger_time": trig.get("trigger_time", ""),
                "sealed_second_board": outcome.get("sealed_second_board"),
                "next_day_open_pct": outcome.get("next_day_open_pct"),
                "trigger_data_mode": trig.get("data_mode"),
                "outcome_data_mode": outcome.get("data_mode"),
            })
        total = len(audit.picks)
        return {
            "as_of_day": as_of_day, "target_day": target_day,
            "data_mode": "ok", "total": total,
            "triggered_count": triggered,
            "trigger_rate": round(triggered / total, 4) if total else 0.0,
            "equals_baseline": audit.equals_baseline,
            "confidence_label": audit.confidence_label,
            "window": {"start": window_start, "end": window_end},
            "per_pick": per_pick,
            "notes": [
                "盘中触发=09:31-10:00 过前高/买点;次日结果=封板/开盘涨幅。",
                "样本不足时 confidence_label=exploratory,勿过度解读。",
            ],
        }

    return _call_store(_run)
```

> 实现注记:核对 `get_strategy_decision_packet` 与 `get_second_board_next_day_outcomes` 的真实签名与返回结构(grep 它们的 def + 返回 dict 的 key);上面 helper 里对 target_day_replay/results/outcomes 的取键按实际调整。两 helper 已 try/except 降级,字段拿不到→triggered=None / outcome=None,不崩。

- [ ] **Step 4: 运行确认通过**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_mcp_selection_audit_tools.py -v`
Expected: 全部 PASS(3 + 2 = 5)。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/mcp/server.py tests/test_mcp_selection_audit_tools.py
git commit -m "feat(#4): get_selection_trigger_validation 闭环对照工具 (盘中触发+次日结果)"
```

---

## Task 7: runner 次日自动验证钩子

**Files:**
- Modify: `src/aegis_alpha/runner.py`
- Modify: `config/runner.yaml`
- Test: `tests/test_runner_selection_validation.py`

- [ ] **Step 1: 写测试**

Create `tests/test_runner_selection_validation.py`:

```python
from __future__ import annotations

from aegis_alpha.runner import AegisAlphaRunner


def _runner(tmp_path):
    # connect=False to avoid opening a real websocket
    r = AegisAlphaRunner(connect=False)
    return r


def test_validation_advisory_never_raises(monkeypatch, tmp_path):
    r = AegisAlphaRunner(connect=False)
    # Force the inner validation to blow up; the hook must swallow it.
    def boom(*a, **k):
        raise RuntimeError("validation exploded")
    monkeypatch.setattr(r, "_run_selection_validation", boom, raising=False)
    # validate_selections_next_day must not raise even if inner work throws
    try:
        r.validate_selections_next_day()
    except Exception as exc:  # pragma: no cover
        assert False, f"hook must be advisory, raised: {exc}"


def test_validation_skips_when_no_prior_audit(monkeypatch, tmp_path):
    r = AegisAlphaRunner(connect=False)
    # no audits in store → returns without alerting, no exception
    result = r.validate_selections_next_day()
    assert result is None or result == [] or isinstance(result, list)
```

> 实现注记:核对 `AegisAlphaRunner.__init__` 是否接受 `connect=False`(runner.py:180 显示 `*, connect: bool = True` —— 是)。若构造仍需 config 文件,传 `AegisAlphaRunner(connect=False)` 应走默认 config。如果默认 config 在测试环境缺失导致构造失败,改用 `monkeypatch` 注入最小 config 或 BLOCKED 上报。

- [ ] **Step 2: 运行确认失败**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_runner_selection_validation.py -v`
Expected: FAIL（方法未定义）。

- [ ] **Step 3: 实现 runner 钩子**

在 `runner.py` 的 `AegisAlphaRunner` 类内(`detect_buypoints_in_window` 附近)追加:

```python
    def validate_selections_next_day(self) -> list:
        """次日自动对照昨收选股审计 vs 今日盘中触发,写 SELECTION_VALIDATION 告警。

        Advisory: 任何异常都被吞,runner liveness 绝不依赖此方法。只读审计 + 写 AgentAlert。
        """
        try:
            cfg = self.config.get("selection_validation", {}) or {}
            if not cfg.get("enabled", False):
                return []
            after = str(cfg.get("after", "10:00"))
            now_hhmm = now_dt().strftime("%H:%M")
            if now_hhmm < after:
                return []
            return self._run_selection_validation()
        except Exception:
            # advisory: never kill the runner cycle
            return []

    def _run_selection_validation(self) -> list:
        from aegis_alpha.alerts.store import AlertStore
        from aegis_alpha.alerts.notifier import notify_macos
        from aegis_alpha.mcp.server import get_selection_trigger_validation

        today = now_dt().date().isoformat()
        # find the most recent prior audit day (best-effort: yesterday's calendar date is fine for now)
        prior_audit = self._latest_prior_selection_audit(today)
        if prior_audit is None:
            return []
        as_of = prior_audit.as_of_day
        result = get_selection_trigger_validation(as_of, today)
        if not isinstance(result, dict) or result.get("data_mode") != "ok":
            return []
        alert_store = AlertStore(self.store)
        event_id = f"selection_validation:{as_of}:{today}"
        body = (
            f"昨收({as_of})选股 vs 今日触发: {result.get('triggered_count')}/{result.get('total')} 触发, "
            f"trigger_rate={result.get('trigger_rate')}, equals_baseline={result.get('equals_baseline')}, "
            f"confidence={result.get('confidence_label')}"
        )
        alert = alert_store.create(
            title=f"SELECTION_VALIDATION {as_of}->{today}",
            body=body[:480], severity="info", event_id=event_id,
        )
        notify_macos(alert)
        return [result]

    def _latest_prior_selection_audit(self, today: str):
        """取早于 today 的最近一条选股审计;无则 None。"""
        try:
            # reuse store: scan distinct as_of_day < today, pick max
            with self.store._connect() as conn:
                row = conn.execute(
                    "SELECT as_of_day FROM selection_audits WHERE as_of_day < ? "
                    "ORDER BY as_of_day DESC LIMIT 1",
                    (today,),
                ).fetchone()
            if row is None:
                return None
            return self.store.get_selection_audit_by_day(row[0])
        except Exception:
            return None
```

在 `run_once` 里,紧跟 `self.detect_buypoints_in_window(symbols)` 之后(同一个 try 块或相邻),加一行调用(advisory,已内部吞异常):

```python
                self.validate_selections_next_day()
```

确认 runner.py 顶部已 import `now_dt`(detect_buypoints_in_window 在用 `now_dt()`——是)。

- [ ] **Step 4: 配置**

在 `config/runner.yaml` 末尾追加:

```yaml
selection_validation:
  enabled: true
  after: "10:00"
```

- [ ] **Step 5: 运行确认通过 + 全套回归**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest tests/test_runner_selection_validation.py -v`
Expected: 2 PASS。
Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest -q`
Expected: 601 + 新增(约 625)全部 PASS,零失败/错误。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/runner.py config/runner.yaml tests/test_runner_selection_validation.py
git commit -m "feat(#4): runner 次日自动选股验证钩子 + SELECTION_VALIDATION 告警 (advisory 隔离)"
```

---

## Task 8: SKILL 文档 + 全套回归收尾

**Files:**
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: SKILL 收录 3 个新工具 + 闭环工作流**

在 "Required MCP Tools" 列表加:
```
- `record_selection_audit`
- `get_selection_audit`
- `get_selection_trigger_validation`
```

在工具说明区加一段(中文,匹配文档风格):
```
闭环验证(二期A):收盘 agent 从候选池选完 TopN 后,调 `record_selection_audit(as_of_day, picks_json, rejected_json, candidate_pool_size)` 持久化选股决策(含每只的相对理由与缺失数据 caveat、落选 near-miss)。程序自动对比三朴素基准(封单额/封成比/首封时间)并标记 `equals_baseline`——若为 true,说明你的 TopN 等同机械基准、未体现额外 alpha,必须重评或明示。次日用 `get_selection_trigger_validation(as_of_day, target_day)` 对照:每只 pick 的 09:31-10:00 盘中触发(过前高/买点)+ 次日封板/开盘结果,给出触发率与是否赢基准。样本 <10 交易日时 confidence_label=exploratory,不得据单日/小样本下稳定结论。runner 在交易日 10:00 后会自动对昨收审计跑一次验证并发 SELECTION_VALIDATION 告警。
```

- [ ] **Step 2: 全套回归**

Run: `/Users/faillonexie/Projects/aegis-alpha/.venv/bin/python -m pytest -q`
Expected: 全绿,零失败。

- [ ] **Step 3: Commit**

```bash
git add .hermes/skills/second-board-radar/SKILL.md
git commit -m "docs(#3/#4): SKILL 收录选股审计闭环工作流 + 3 个工具"
```

---

## Self-Review

**Spec coverage:**
- 数据模型(SelectionAudit/Pick/Rejected, facts-only)→ Task 1 ✓
- migration m0008 selection_audits → Task 2 ✓
- 纯计算(audit_id 幂等 / equals_baseline / confidence)→ Task 3 ✓
- store 持久化(幂等 upsert / 按日取 / 计数)→ Task 4 ✓
- record_selection_audit + 即时反机械提醒 + get_selection_audit → Task 5 ✓
- get_selection_trigger_validation(#4 盘中触发+次日结果 join)→ Task 6 ✓
- runner 次日自动验证 + SELECTION_VALIDATION 告警 + advisory 隔离 + 配置 → Task 7 ✓
- SKILL 文档 → Task 8 ✓

**Placeholder scan:** 每个 code step 含完整代码。多处"实现注记"给出 grep 命令核对真实字段名/依赖名(now_iso import、_call_store vs get_store、decision_packet/outcome 返回 key、历史二板字段名)并都配降级兜底,非占位符而是明确核对指令。

**Type consistency:**
- `SelectionAudit.picks: list[SelectionPick]`(Task1)→ store `_dump_list`/`model_validate`(Task4)→ 工具 `model_validate`(Task5)一致。
- `compute_audit_id/compute_equals_baseline/compute_confidence_label`(Task3)→ Task5 record 调用一致。
- store `save_selection_audit/get_selection_audit_by_day/count_selection_audit_days`(Task4)→ Task5/6/7 调用一致。
- `get_selection_trigger_validation(as_of_day, target_day, window_start, window_end)`(Task6)→ Task7 runner 调用一致。
- `_validation_intraday_trigger/_validation_next_day_outcome`(Task6)是 monkeypatch 点,测试与实现一致。

**依赖核对(实现时必做,已在注记标出):**
- server 取 store 的真实机制(`_call_store` at server.py:30)——Task5/6 的工具与测试 monkeypatch 必须对齐真实名。
- `get_strategy_decision_packet` / `get_second_board_next_day_outcomes` / `get_historical_second_board_candidates` 的真实返回 key——Task5/6 helper 按实调整,缺失即降级。

## 验收

8 任务完成后:闭环端到端(record→get→trigger_validation→runner 自动告警)跑通;反机械排序固化为 equals_baseline+即时提醒;样本不足强制 exploratory;facts-only 哲学守卫通过;全套测试不回归(601→约625)。

二期后续(本计划外):#6 Wind 真值(待本闭环证明 alpha)、样本累积(需真实交易日)、实盘稳定性。
