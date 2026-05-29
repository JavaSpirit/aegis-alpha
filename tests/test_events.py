from __future__ import annotations

from aegis_alpha.agent_context import signal_snapshot_agent_context
from aegis_alpha.agent_eval import evaluate_agent_replay_response
from aegis_alpha.adapters.jvquant_websocket import summarize_raw_ab_payload, subscription_codes
from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
from aegis_alpha.models import AgentReview, AgentReviewCorrection, CandidateOutcomeReview, SignalSnapshot
from aegis_alpha.replay import run_orderbook_replay_fixture
from aegis_alpha.signals.orderbook import estimate_orderbook_metrics
from aegis_alpha.storage import AegisAlphaStore, ParquetSink, refresh_snapshot_freshness


def test_event_scoring_config_loads() -> None:
    config = load_event_scoring_config()

    assert config.version == 1
    assert config.rules["APPROACHING_LIMIT_UP"].enabled is True
    assert "rescore_second_board_candidates" in config.rules["BIG_ORDER_INFLOW_SPIKE"].agent_action


def test_signal_window_buffer_calculates_speed_and_flow() -> None:
    buffer = SignalWindowBuffer()
    for index, price in enumerate([10.0, 10.1, 10.2, 10.4, 10.6, 10.9]):
        buffer.add_price("600000", f"2026-05-28T09:3{index}:00+08:00", price, 100_000_000, change_pct=9.1)
    buffer.add_big_order_flow("600000", 12_000_000)
    buffer.set_orderbook_quality("600000", 72)

    snapshot = buffer.latest_snapshot(
        "600000",
        received_at="2026-05-28T09:35:30+08:00",
    )

    assert snapshot.change_pct == 9.1
    assert snapshot.orderbook_quality_score == 72
    assert snapshot.speed_1m_pct == 2.8302
    assert snapshot.speed_5m_pct == 9.0
    assert snapshot.big_order_net_inflow_ratio == 0.12
    assert snapshot.freshness_status == "fresh"


def test_orderbook_metrics_estimate_quality_and_seal_decay() -> None:
    strong = estimate_orderbook_metrics(
        price=11.0,
        change_pct=9.9,
        bid_volumes=[100_000, 50_000, 30_000],
        ask_volumes=[10_000, 20_000, 30_000],
    )
    weaker = estimate_orderbook_metrics(
        price=11.0,
        change_pct=9.9,
        bid_volumes=[50_000, 25_000, 15_000],
        ask_volumes=[20_000, 30_000, 40_000],
        previous_seal_amount_cny=strong.seal_amount_cny,
    )

    assert strong.orderbook_quality_score > 70
    assert strong.seal_amount_cny == 110_000_000
    assert weaker.seal_decay_pct == 50.0
    assert weaker.ask_pressure_score > strong.ask_pressure_score


def test_signal_window_buffer_carries_orderbook_metrics() -> None:
    buffer = SignalWindowBuffer()
    buffer.add_price("600000", "2026-05-28T09:35:00+08:00", 11.0, 80_000_000, change_pct=9.9)
    buffer.set_orderbook_metrics(
        "600000",
        quality_score=82.5,
        ask_pressure_score=17.5,
        seal_amount_cny=110_000_000,
        seal_decay_pct=12.0,
        sell_wall_amount_cny=5_000_000,
        notes=["test_orderbook_note"],
    )

    snapshot = buffer.latest_snapshot("600000", received_at="2026-05-28T09:35:01+08:00")

    assert snapshot.orderbook_quality_score == 82.5
    assert snapshot.ask_pressure_score == 17.5
    assert snapshot.seal_amount_cny == 110_000_000
    assert snapshot.seal_decay_pct == 12.0
    assert snapshot.sell_wall_amount_cny == 5_000_000
    assert "test_orderbook_note" in snapshot.notes


def test_event_detector_builds_structured_events() -> None:
    detector = EventDetector(load_event_scoring_config())
    snapshot = SignalSnapshot(
        symbol="600000",
        name="示例股票",
        theme="机器人",
        provider="mock",
        data_mode="mock",
        price=10.9,
        change_pct=9.2,
        speed_1m_pct=1.1,
        speed_3m_pct=2.3,
        speed_5m_pct=3.2,
        speed_10m_pct=4.0,
        big_order_net_inflow_cny=50_000_000,
        big_order_net_inflow_ratio=0.12,
        orderbook_quality_score=76,
        seal_amount_cny=120_000_000,
        seal_decay_pct=35.0,
        data_timestamp="2026-05-28T09:35:00+08:00",
        provider_timestamp="2026-05-28T09:35:00+08:00",
        received_at="2026-05-28T09:35:30+08:00",
        freshness_status="fresh",
    )

    events = detector.detect_from_snapshot(snapshot)
    event_types = {event.event_type for event in events}

    assert "APPROACHING_LIMIT_UP" in event_types
    assert "BIG_ORDER_INFLOW_SPIKE" in event_types
    assert "SEAL_ORDER_DECAY" in event_types
    assert all(event.evidence for event in events)
    assert all(event.suggested_agent_action for event in events)


def test_subscription_code_generation() -> None:
    assert subscription_codes(["600519.SH", "000001"], ["lv1", "lv2", "bad"]) == [
        "lv1_600519",
        "lv2_600519",
        "lv1_000001",
        "lv2_000001",
    ]


def test_raw_websocket_payload_summary() -> None:
    summary = summarize_raw_ab_payload(
        "lv2_600519=09:30:00,1,100.1,400|09:30:01,2,100.2,500\n"
        "lv10_600519=09:30:01,茅台,100.2,99.0,1000000,1000,100.1,100.0,99.9,99.8,99.7,99.6,99.5,99.4,99.3,99.2,1,2,3,4,5,6,7,8,9,10,100.3,100.4,100.5,100.6,100.7,100.8,100.9,101.0,101.1,101.2,10,9,8,7,6,5,4,3,2,1"
    )

    assert summary["levels"]["lv2"]["latest_field_counts"] == [4]
    assert summary["levels"]["lv2"]["max_piece_count"] == 2
    assert summary["levels"]["lv10"]["latest_field_counts"] == [46]


def test_sqlite_store_roundtrip(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    detector = EventDetector(load_event_scoring_config())
    snapshot = SignalSnapshot(
        symbol="600000",
        data_timestamp="2026-05-28T09:35:00+08:00",
        provider_timestamp="2026-05-28T09:35:00+08:00",
        received_at="2026-05-28T09:35:01+08:00",
        freshness_status="fresh",
        change_pct=9.5,
        speed_5m_pct=2.0,
        big_order_net_inflow_cny=40_000_000,
        big_order_net_inflow_ratio=0.10,
    )
    events = detector.detect_from_snapshot(snapshot)

    store.save_signal_snapshot(snapshot)
    store.save_market_events(events)
    store.save_review_outcome(CandidateOutcomeReview(symbol="600000", trading_day="2026-05-28"))

    assert store.latest_signal_snapshot("600000") is not None
    assert store.recent_market_events()
    assert store.get_review_outcome("600000", "2026-05-28").symbol == "600000"
    assert ParquetSink(tmp_path / "parquet").status()["root"].endswith("parquet")


def test_agent_review_store_roundtrip(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    review = store.save_agent_review(
        AgentReview(
            run_type="historical_snapshot_eval",
            target_time="2026-05-29T10:00:00+08:00",
            symbols=["600519", "000001"],
            provider="deepseek",
            model="deepseek-v4-pro",
            passed=True,
            grades=["C", "REJECT"],
            summary={"grade_counts": {"C": 1, "REJECT": 1}},
            payload={"example": True},
        )
    )

    reviews = store.recent_agent_reviews()

    assert review.review_id
    assert reviews[0].passed is True
    assert reviews[0].grades == ["C", "REJECT"]


def test_agent_review_correction_summary_suggests_skill_patch(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-1",
            symbol="600519",
            correction_type="STRATEGY_ERROR",
            expected_grade="REJECT",
            comment="盘口质量和同题材联动不足，不应该给 C。",
        )
    )
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-2",
            symbol="600519",
            correction_type="STRATEGY_ERROR",
            expected_grade="REJECT",
            comment="又一次偏乐观，需要降低评级。",
        )
    )

    corrections = store.recent_agent_review_corrections(limit=5)
    summary = store.agent_correction_summary(limit=10)

    assert corrections[0].correction_id
    assert summary.total_count == 2
    assert summary.by_type["STRATEGY_ERROR"] == 2
    assert summary.by_symbol["600519"] == 2
    assert "lower the grade" in summary.suggested_skill_patch
    assert "skill" in summary.recommended_next_action.lower()
    assert {action.target for action in summary.recommended_actions} == {"scoring_config", "skill"}
    assert all(action.correction_type == "STRATEGY_ERROR" for action in summary.recommended_actions)


def test_agent_review_correction_summary_routes_data_unit_and_expression_errors(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-data",
            correction_type="DATA_ERROR",
            comment="数据时间戳过期，不能继续评级。",
        )
    )
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-unit",
            correction_type="UNIT_ERROR",
            comment="把 speed_5m_pct 当成比例放大了。",
        )
    )
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-expression",
            correction_type="EXPRESSION_RISK",
            comment="表达像直接下单指令。",
        )
    )

    summary = store.agent_correction_summary(limit=10)
    actions = {(action.target, action.correction_type) for action in summary.recommended_actions}

    assert ("adapter", "DATA_ERROR") in actions
    assert ("memory", "UNIT_ERROR") in actions
    assert ("skill", "EXPRESSION_RISK") in actions
    assert any(action.status == "ready_to_apply" for action in summary.recommended_actions)
    assert any(
        action.correction_type == "EXPRESSION_RISK" and "direct buy/sell commands" in action.suggested_patch
        for action in summary.recommended_actions
    )
    assert summary.suggested_memory


def test_correction_action_proposal_decision_workflow(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-unit",
            correction_type="UNIT_ERROR",
            comment="字段单位解释错了。",
        )
    )

    summary = store.agent_correction_summary(limit=10)
    proposals = store.save_correction_action_proposals(summary)
    pending = store.pending_correction_action_proposals()

    assert len(proposals) == 1
    assert pending[0].target == "memory"
    assert pending[0].status == "pending"

    decided = store.record_correction_action_decision(
        pending[0].proposal_id,
        decision="approve",
        note="确认这是稳定项目记忆。",
        decided_by="tester",
    )
    history = store.correction_action_history()

    assert decided.status == "approved"
    assert decided.decisions[0].decision == "approve"
    assert decided.decisions[0].previous_status == "pending"
    assert not store.pending_correction_action_proposals()
    assert history[0].status == "approved"
    assert history[0].decisions[0].decided_by == "tester"


def test_refresh_snapshot_freshness_marks_old_data_stale() -> None:
    snapshot = SignalSnapshot(
        symbol="600000",
        data_timestamp="2000-01-01T09:35:00+08:00",
        provider_timestamp="2000-01-01T09:35:00+08:00",
        received_at="2000-01-01T09:35:01+08:00",
        freshness_status="fresh",
    )

    refreshed = refresh_snapshot_freshness(snapshot)

    assert refreshed.freshness_status == "stale"
    assert any(note.startswith("freshness_status_refreshed_at=") for note in refreshed.notes)


def test_orderbook_replay_fixture_triggers_expected_events() -> None:
    snapshot, events = run_orderbook_replay_fixture()
    event_types = {event.event_type for event in events}

    assert snapshot.data_mode == "offline_replay"
    assert snapshot.freshness_status == "fresh"
    assert snapshot.speed_5m_pct > 1.5
    assert snapshot.big_order_net_inflow_ratio > 0.08
    assert snapshot.seal_decay_pct >= 30.0
    assert "APPROACHING_LIMIT_UP" in event_types
    assert "BIG_ORDER_INFLOW_SPIKE" in event_types
    assert "SEAL_ORDER_DECAY" in event_types
    assert "SECOND_BOARD_CANDIDATE_REPRICE" in event_types


def test_agent_replay_response_evaluation() -> None:
    content = """
    {
      "grade": "B",
      "natural_language_reason": "这是离线合成回放，盘口指标只能说明规则链路触发，不能当作真实行情。",
      "data_facts": ["freshness_status=stale"],
      "rule_score": "封单衰减较高",
      "risks": ["非真实行情"],
      "trigger_conditions": {"price": [], "volume": [], "theme": [], "orderbook": []},
      "avoid_conditions": ["数据过期"],
      "freshness_warning": "stale",
      "data_timestamp": "2000-01-01T09:35:00+08:00",
      "disclaimer": "仅供研究观察，非投资建议。"
    }
    """

    result = evaluate_agent_replay_response(content, expected_freshness_status="stale")

    assert result["passed"] is True
    assert result["parsed"]["grade"] == "B"


def test_agent_evaluation_accepts_per_symbol_grades() -> None:
    content = """
    {
      "market_context": "历史回放截面，不是当前实时行情。",
      "per_symbol": [
        {
          "symbol": "600519",
          "grade": "C",
          "natural_language_reason": "涨幅低且无封单，不适合打板观察。"
        },
        {
          "symbol": "000001",
          "grade": "REJECT",
          "natural_language_reason": "大单净流入为零，盘口质量低。"
        }
      ],
      "overall_conclusion": "均不适合。",
      "disclaimer": "本分析基于历史回放数据，不构成任何投资建议。"
    }
    """

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is True


def test_agent_evaluation_accepts_trade_instruction_disclaimer() -> None:
    content = """
    {
      "market_context": "历史回放截面。",
      "per_symbol": [
        {
          "symbol": "600519",
          "grade": "C",
          "natural_language_reason": "涨幅低且无封单，不适合打板观察。"
        }
      ],
      "overall_conclusion": "不适合。",
      "disclaimer": "本分析仅用于研究目的，不构成任何形式的交易建议或操作指令。"
    }
    """

    result = evaluate_agent_replay_response(content, expected_freshness_status="fresh")

    assert result["passed"] is True


def test_signal_snapshot_agent_context_documents_pct_units() -> None:
    context = signal_snapshot_agent_context()

    assert "0.0929%" in context["field_units"]["speed_10m_pct"]
    assert "3.11%" in context["field_units"]["big_order_net_inflow_ratio"]
    assert any("_pct" in rule and "0.0929%" in rule for rule in context["interpretation_rules"])
