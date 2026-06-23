from __future__ import annotations

from aegis_alpha.models import AgentObservation
from aegis_alpha.feedback.agent_observation import (
    compute_observation_id,
    observation_notification_grade,
)


def _obs(**kw) -> AgentObservation:
    base = dict(trading_day="2026-06-23")
    base.update(kw)
    return AgentObservation(**base)


def test_compute_observation_id_stable_and_order_independent():
    a = compute_observation_id(
        trading_day="2026-06-23", source="periodic_market_scan",
        observation_type="theme_rotation", theme="AI算力",
    )
    b = compute_observation_id(
        trading_day="2026-06-23", source="periodic_market_scan",
        observation_type="theme_rotation", theme="AI算力",
    )
    assert a == b
    assert a.startswith("ob_")


def test_compute_observation_id_distinguishes_type():
    a = compute_observation_id(
        trading_day="2026-06-23", source="periodic_market_scan",
        observation_type="theme_rotation", symbol="002491",
    )
    b = compute_observation_id(
        trading_day="2026-06-23", source="periodic_market_scan",
        observation_type="buy_point_quality", symbol="002491",
    )
    assert a != b


def test_symbol_case_insensitive_in_id():
    a = compute_observation_id(
        trading_day="2026-06-23", source="manual_wechat_query",
        observation_type="buy_point_quality", symbol="sh600519",
    )
    b = compute_observation_id(
        trading_day="2026-06-23", source="manual_wechat_query",
        observation_type="buy_point_quality", symbol="SH600519",
    )
    assert a == b


# --- grade: urgent ---

def test_urgent_high_confidence_buy_point():
    obs = _obs(observation_type="buy_point_quality", stance="actionable_watch", confidence="high")
    assert observation_notification_grade(obs) == "urgent"


# --- grade: important ---

def test_important_medium_confidence_buy_point():
    obs = _obs(observation_type="buy_point_quality", stance="actionable_watch", confidence="medium")
    assert observation_notification_grade(obs) == "important"


def test_important_regime_shift_high():
    obs = _obs(observation_type="market_regime_shift", stance="actionable_watch", confidence="high")
    assert observation_notification_grade(obs) == "important"


def test_important_theme_rotation_medium():
    obs = _obs(observation_type="theme_rotation", stance="actionable_watch", confidence="medium")
    assert observation_notification_grade(obs) == "important"


def test_important_strong_continuation_high():
    obs = _obs(
        observation_type="strong_continuation_without_buy_point",
        stance="actionable_watch", confidence="high",
    )
    assert observation_notification_grade(obs) == "important"


# --- grade: watch ---

def test_watch_low_confidence_buy_point():
    obs = _obs(observation_type="buy_point_quality", stance="actionable_watch", confidence="low")
    assert observation_notification_grade(obs) == "watch"


def test_watch_low_confidence_theme_rotation():
    obs = _obs(observation_type="theme_rotation", stance="actionable_watch", confidence="low")
    assert observation_notification_grade(obs) == "watch"


def test_watch_monitor_only_stance():
    obs = _obs(observation_type="watchlist_observation", stance="monitor_only", confidence="high")
    assert observation_notification_grade(obs) == "watch"


def test_watch_high_confidence_data_gap():
    obs = _obs(observation_type="data_gap", stance="actionable_watch", confidence="high")
    assert observation_notification_grade(obs) == "watch"


def test_watch_actionable_watchlist_observation():
    obs = _obs(observation_type="watchlist_observation", stance="actionable_watch", confidence="high")
    assert observation_notification_grade(obs) == "watch"


# --- grade: suppress ---

def test_suppress_insufficient_data_stance():
    obs = _obs(observation_type="buy_point_quality", stance="insufficient_data", confidence="high")
    assert observation_notification_grade(obs) == "suppress"


def test_suppress_reject_stance():
    obs = _obs(observation_type="buy_point_quality", stance="reject", confidence="high")
    assert observation_notification_grade(obs) == "suppress"


def test_suppress_noise_type():
    obs = _obs(observation_type="noise_or_rejected_trigger", stance="actionable_watch", confidence="high")
    assert observation_notification_grade(obs) == "suppress"


def test_suppress_low_confidence_data_gap():
    obs = _obs(observation_type="data_gap", stance="actionable_watch", confidence="low")
    assert observation_notification_grade(obs) == "suppress"
