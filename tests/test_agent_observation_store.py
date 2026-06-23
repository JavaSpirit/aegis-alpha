from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.models import AgentObservation
from aegis_alpha.storage import AegisAlphaStore


def test_agent_observations_table_exists(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))  # applies migrations on init
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_observations'"
        ).fetchone()
    assert row is not None


def test_agent_observations_columns(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_observations)").fetchall()}
    expected = {
        "observation_id", "trading_day", "source", "observation_type",
        "symbol", "theme", "stance", "confidence", "expires_at",
        "created_at", "payload_json",
    }
    assert expected <= cols


def test_save_and_get_agent_observation(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    obs = AgentObservation(
        observation_id="ob_test1",
        trading_day="2026-06-23",
        source="periodic_market_scan",
        observation_type="theme_rotation",
        theme="AI算力",
        title="算力主题轮动",
        summary="多只算力股盘中拉升",
        stance="actionable_watch",
        confidence="medium",
        evidence=["3只同题材5分钟涨速>5%"],
        data_gaps=["无分钟级主动买盘方向"],
    )
    store.save_agent_observation(obs)
    got = store.get_agent_observation("ob_test1")
    assert got is not None
    assert got.theme == "AI算力"
    assert got.stance == "actionable_watch"
    assert got.evidence == ["3只同题材5分钟涨速>5%"]
    assert got.data_gaps == ["无分钟级主动买盘方向"]


def test_save_sets_created_at_when_missing(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    obs = AgentObservation(observation_id="ob_ts", trading_day="2026-06-23")
    saved = store.save_agent_observation(obs)
    assert saved.created_at  # auto-stamped
    got = store.get_agent_observation("ob_ts")
    assert got is not None
    assert got.created_at == saved.created_at


def test_save_agent_observation_dedup_returns_existing(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    first = AgentObservation(
        observation_id="ob_dup", trading_day="2026-06-23",
        title="first", stance="actionable_watch",
    )
    store.save_agent_observation(first)
    # Same observation_id with different content must NOT overwrite — dedup.
    second = AgentObservation(
        observation_id="ob_dup", trading_day="2026-06-23",
        title="second-should-be-ignored", stance="reject",
    )
    returned = store.save_agent_observation(second)
    assert returned.title == "first"
    assert returned.stance == "actionable_watch"
    got = store.get_agent_observation("ob_dup")
    assert got is not None
    assert got.title == "first"


def test_list_agent_observations_filters(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    store.save_agent_observation(AgentObservation(
        observation_id="o1", trading_day="2026-06-23",
        observation_type="theme_rotation", symbol="",
    ))
    store.save_agent_observation(AgentObservation(
        observation_id="o2", trading_day="2026-06-23",
        observation_type="buy_point_quality", symbol="002491",
    ))
    store.save_agent_observation(AgentObservation(
        observation_id="o3", trading_day="2026-06-20",
        observation_type="theme_rotation", symbol="",
    ))

    by_day = store.list_agent_observations(trading_day="2026-06-23")
    assert {o.observation_id for o in by_day} == {"o1", "o2"}

    by_type = store.list_agent_observations(observation_type="theme_rotation")
    assert {o.observation_id for o in by_type} == {"o1", "o3"}

    by_symbol = store.list_agent_observations(symbol="002491")
    assert {o.observation_id for o in by_symbol} == {"o2"}


def test_get_agent_observation_missing_returns_none(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    assert store.get_agent_observation("nope") is None
