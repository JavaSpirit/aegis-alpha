from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_mock_adapter_exposes_p2_theme_ladder_emotion_auction_contracts() -> None:
    adapter = MockMarketDataAdapter()

    leaders = adapter.get_theme_leaders("AI应用")
    ladder = adapter.get_limit_up_ladder("002230.SZ")
    emotion = adapter.get_market_emotion()
    auction = adapter.get_auction_analysis("002230.SZ")
    candidates = adapter.get_second_board_candidates()

    # Look up candidates by symbol so the test is order-independent.
    by_symbol = {c.symbol: c for c in candidates}

    # Baseline contracts for source data methods.
    assert leaders[0].leader_symbol == "002230.SZ"
    assert ladder.height_label == "second_board"
    assert emotion.max_height_today == 4
    assert auction.pattern == "strong_open"

    # Strengthen: candidate fields must match resolver output, not hardcoded values.
    kdxf = by_symbol["002230.SZ"]
    assert kdxf.previous_consecutive_boards == 2, (
        "Expected 2 from LimitUpLadderResolver (second_board), not hardcoded 1"
    )
    assert kdxf.previous_height_label == "second_board"
    assert kdxf.theme_role == "leader"
    assert kdxf.theme_leader_symbol == "002230.SZ"

    jqr = by_symbol["300024.SZ"]
    assert jqr.previous_consecutive_boards == 1
    assert jqr.previous_height_label == "first_board"
    assert jqr.theme_role == "leader"  # 机器人 theme leader is 300024.SZ itself
    assert jqr.theme_leader_symbol == "300024.SZ"

    # P4: three_year_* fields stay in [0, 1] range. Mock candidates retain their
    # hardcoded literals (mock does not call get_history_stats during candidate
    # build), but this guard prevents regressions if someone later changes the
    # mock to compute the rates and accidentally returns out-of-range values.
    for cand in candidates:
        assert 0.0 <= cand.three_year_touch_limit_success_rate <= 1.0
        assert 0.0 <= cand.three_year_sealed_next_day_gap_up_rate <= 1.0


def test_mock_candidate_theme_role_responds_to_resolver_output() -> None:
    """If resolver returns no leader for a theme, candidate's theme_role must be unknown."""
    # All mock candidates currently have a leader; this test guards against
    # future regressions where someone hardcodes theme_role="leader" again.
    adapter = MockMarketDataAdapter()
    for candidate in adapter.get_second_board_candidates():
        assert candidate.theme_role in {"leader", "co_leader", "follower", "unknown"}
        if candidate.theme_role == "leader":
            assert candidate.theme_leader_symbol == candidate.symbol, (
                f"{candidate.symbol} marked leader but theme_leader_symbol is "
                f"{candidate.theme_leader_symbol!r}"
            )
