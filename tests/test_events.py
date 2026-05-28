from __future__ import annotations

from aegis_alpha.adapters.jvquant_websocket import summarize_raw_ab_payload, subscription_codes
from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
from aegis_alpha.models import CandidateOutcomeReview, SignalSnapshot
from aegis_alpha.storage import AegisAlphaStore, ParquetSink


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
