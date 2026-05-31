from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import OutcomeAttribution
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_attribution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attribution = OutcomeAttribution(
        attribution_id="abc123",
        symbol="002230.SZ",
        trading_day="2026-05-31",
        primary_tag="leader_break_down",
        secondary_tags=["auction_high_open_too_far"],
        evidence=["Leader X broken at 13:30"],
        created_at="2026-05-31T15:30:00+08:00",
    )

    store.save_attribution(attribution)
    fetched = store.get_attribution("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.primary_tag == "leader_break_down"
    assert fetched.secondary_tags == ["auction_high_open_too_far"]


def test_list_attributions_by_tag(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="1",
            symbol="A",
            trading_day="2026-05-30",
            primary_tag="leader_break_down",
            created_at="2026-05-30T15:30:00+08:00",
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="2",
            symbol="B",
            trading_day="2026-05-31",
            primary_tag="market_gate_turned_avoid",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="3",
            symbol="C",
            trading_day="2026-05-31",
            primary_tag="leader_break_down",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )

    rows = store.list_attributions(primary_tag="leader_break_down")

    assert {row.symbol for row in rows} == {"A", "C"}
