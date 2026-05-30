from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_mock_adapter_exposes_p2_theme_ladder_emotion_auction_contracts() -> None:
    adapter = MockMarketDataAdapter()

    leaders = adapter.get_theme_leaders("AI应用")
    ladder = adapter.get_limit_up_ladder("002230.SZ")
    emotion = adapter.get_market_emotion()
    auction = adapter.get_auction_analysis("002230.SZ")
    candidate = adapter.get_second_board_candidates()[0]

    assert leaders[0].leader_symbol == "002230.SZ"
    assert ladder.height_label == "second_board"
    assert emotion.max_height_today == 4
    assert auction.pattern == "strong_open"
    assert candidate.previous_consecutive_boards == 1
    assert candidate.theme_role == "leader"
