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


def test_get_attribution_returns_none_when_missing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    fetched = store.get_attribution("UNKNOWN", "2026-05-31")

    assert fetched is None


def test_list_attributions_filters_by_date_range(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day in ("2026-05-25", "2026-05-26", "2026-05-30"):
        store.save_attribution(
            OutcomeAttribution(
                attribution_id=f"id-{day}",
                symbol="X",
                trading_day=day,
                primary_tag="leader_break_down",
                created_at=f"{day}T15:30:00+08:00",
            )
        )

    rows = store.list_attributions(start_day="2026-05-26", end_day="2026-05-29")

    assert {row.trading_day for row in rows} == {"2026-05-26"}


def test_list_attributions_filters_by_symbol(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="x1",
            symbol="X",
            trading_day="2026-05-31",
            primary_tag="leader_break_down",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="y1",
            symbol="Y",
            trading_day="2026-05-31",
            primary_tag="leader_break_down",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )

    rows = store.list_attributions(symbol="Y")

    assert len(rows) == 1
    assert rows[0].symbol == "Y"


def test_save_attribution_upsert_preserves_created_at(tmp_path: Path) -> None:
    import sqlite3
    store = _store(tmp_path)
    original_ts = "2026-05-31T09:30:00+08:00"
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="abc",
            symbol="X",
            trading_day="2026-05-31",
            primary_tag="leader_break_down",
            created_at=original_ts,
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="abc",
            symbol="X",
            trading_day="2026-05-31",
            primary_tag="market_gate_turned_avoid",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT created_at FROM outcome_attributions WHERE attribution_id = ?",
            ("abc",),
        ).fetchone()

    assert row is not None
    assert row[0] == original_ts
