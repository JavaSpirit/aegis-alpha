from __future__ import annotations

from aegis_alpha.models import LadderEntry, ThemeLeader
from aegis_alpha.storage import AegisAlphaStore


def test_theme_leader_storage_roundtrip(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    leader = ThemeLeader(
        theme="机器人",
        trading_day="2026-05-29",
        leader_symbol="600000",
        leader_name="示例股份",
        member_count=3,
    )

    store.save_theme_leaders([leader])

    assert store.latest_theme_leaders("机器人")[0].leader_symbol == "600000"


def test_ladder_storage_roundtrip(tmp_path) -> None:
    store = AegisAlphaStore(tmp_path / "aegis_alpha.db")
    entry = LadderEntry(
        symbol="600000",
        trading_day="2026-05-29",
        consecutive_boards=3,
        height_label="third_board",
    )

    store.save_ladder_entries([entry])

    loaded = store.get_ladder_entry("600000", "2026-05-29")
    assert loaded is not None
    assert loaded.height_label == "third_board"
