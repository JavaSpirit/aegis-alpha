from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.feedback.attribution import attribute_from_stored_data
from aegis_alpha.models import CandidateOutcomeReview, HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def test_attribute_uses_outcome_and_historical_snapshot(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    snap = HistoricalCandidateSnapshot(
        symbol="300024.SZ",
        trading_day="2026-05-31",
        grade_at_pick="C",
        theme="机器人",
        theme_role="leader",
        previous_consecutive_boards=1,
        payload_json='{"auction_change_pct": 1.5, "first_limit_up_time": "13:50:00", "seal_decay_pct": 0.0}',
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="300024.SZ",
            trading_day="2026-05-31",
            touched_limit_up=False,
            sealed_second_board=False,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="300024.SZ",
        trading_day="2026-05-31",
    )

    assert attribution is not None
    # late seal time (13:50:00) should produce first_seal_too_late
    assert attribution.primary_tag == "first_seal_too_late"


def test_attribute_returns_none_when_outcome_missing(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="UNKNOWN",
        trading_day="2026-05-31",
    )

    assert attribution is None


def test_attribute_returns_no_attribution_when_sealed(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()
    snap = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="A",
        theme="AI应用",
        theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"auction_change_pct": 1.0, "first_limit_up_time": "09:35:00", "seal_decay_pct": 0.0}',
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            sealed_second_board=True,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="002230.SZ",
        trading_day="2026-05-31",
    )

    assert attribution is not None
    assert attribution.primary_tag == "no_clear_attribution"


def test_attribute_returns_none_when_snapshot_missing(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()
    # Outcome exists but no historical snapshot
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            sealed_second_board=False,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="002230.SZ",
        trading_day="2026-05-31",
    )

    assert attribution is None


def test_attribute_handles_malformed_payload_json(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()
    snap = HistoricalCandidateSnapshot(
        symbol="X",
        trading_day="2026-05-31",
        grade_at_pick="C",
        theme="AI",
        theme_role="leader",
        previous_consecutive_boards=1,
        payload_json="not-json",
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="X",
            trading_day="2026-05-31",
            sealed_second_board=False,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="X",
        trading_day="2026-05-31",
    )

    # Malformed JSON degrades gracefully: defaults applied, mock gate break_board_rate is low,
    # leader_role is leader so leader_break_down can't fire, no other signal triggers.
    assert attribution is not None
    assert attribution.primary_tag == "no_clear_attribution"


def test_attribute_handles_adapter_exception_with_fallback(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")

    class FailingAdapter:
        # Subclasses MockMarketDataAdapter behavior just enough to surface failures.
        def get_seal_timeline(self, symbol: str, trading_day: str = ""):
            raise RuntimeError("seal timeline service unavailable")

        def get_market_sentiment_gate(self):
            raise RuntimeError("gate service unavailable")

    snap = HistoricalCandidateSnapshot(
        symbol="X",
        trading_day="2026-05-31",
        grade_at_pick="C",
        theme="AI",
        theme_role="follower",
        previous_consecutive_boards=1,
        payload_json='{"auction_change_pct": 1.0, "first_limit_up_time": "09:30:00", "seal_decay_pct": 0.0, "theme_leader_symbol": "LDR"}',
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="X",
            trading_day="2026-05-31",
            sealed_second_board=False,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=FailingAdapter(),
        store=store,
        symbol="X",
        trading_day="2026-05-31",
    )

    # Both adapter calls fail, fallback to leader_status="unknown" + market_break_board_rate=0.0.
    # follower with leader_status="unknown" doesn't trigger leader_break_down (needs "broken"),
    # break_board_rate=0.0 < 0.45 so Rule 1 doesn't fire either,
    # auction is below threshold, no seal decay, on-time first seal — falls through to no_clear.
    assert attribution is not None
    assert attribution.primary_tag == "no_clear_attribution"
