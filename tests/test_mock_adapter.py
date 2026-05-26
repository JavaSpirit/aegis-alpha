from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_explain_candidate_contract() -> None:
    explanation = MockMarketDataAdapter().explain_candidate("600000.SH").model_dump()

    assert explanation["grade"] in {"A", "B", "C", "REJECT"}
    assert explanation["observations"]
    assert explanation["risks"]
    assert explanation["trigger_conditions"]
    assert explanation["avoid_conditions"]
    assert explanation["data_timestamp"]
    assert "not investment advice" in explanation["disclaimer"].lower()


def test_read_only_tool_shapes() -> None:
    adapter = MockMarketDataAdapter()

    assert adapter.get_market_snapshot().limit_up_count >= 0
    assert adapter.get_market_sentiment_gate().action in {"active", "selective", "defensive", "avoid"}
    assert adapter.get_limitup_pool()
    assert adapter.get_break_board_pool()
    assert adapter.get_stock_realtime_snapshot("600000.SH").symbol == "600000.SH"
    assert adapter.get_stock_orderbook_snapshot("600000.SH").bid_levels
    assert adapter.get_stock_history_limitup_stats("600000.SH").sample_size > 0
    assert adapter.get_theme_strength("600000.SH").strength_score >= 0
    assert adapter.get_second_board_candidates()


def test_second_board_explanation_contract() -> None:
    explanation = MockMarketDataAdapter().explain_second_board_candidate("002230.SZ").model_dump()

    assert explanation["grade"] in {"A", "B", "C", "REJECT"}
    assert explanation["observations"]
    assert explanation["trigger_conditions"]
    assert explanation["avoid_conditions"]
    assert "not investment advice" in explanation["disclaimer"].lower()
