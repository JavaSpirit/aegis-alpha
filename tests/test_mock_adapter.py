from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_explain_candidate_contract() -> None:
    explanation = MockMarketDataAdapter().explain_candidate("600000.SH").model_dump()

    assert explanation["grade"] in {"A", "B", "C", "REJECT"}
    assert explanation["grade_reason"]
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
    assert explanation["grade_reason"]
    assert explanation["observations"]
    assert explanation["trigger_conditions"]
    assert explanation["avoid_conditions"]
    assert "not investment advice" in explanation["disclaimer"].lower()


def test_mock_second_board_candidate_includes_limitup_driver_type():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    assert candidates, "mock should return at least one candidate"
    for cand in candidates:
        assert hasattr(cand, "limitup_driver_type")
        assert cand.limitup_driver_type in {"earnings", "policy", "theme", "hot_money", "unknown"}


def test_mock_candidate_driver_inferred_from_concept_tags():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    drivers = {c.limitup_driver_type for c in candidates}
    # mock 至少给出一个非 unknown 的样本，便于 Hermes 演示该字段
    assert drivers - {"unknown"}, f"mock should include at least one non-unknown driver, got: {drivers}"


def test_mock_candidate_intraday_pattern_in_allowed_set():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    allowed = {"one_word_board", "t_shape_board", "messy_board",
               "platform_breakout", "false_breakout", "normal", "unknown"}
    for cand in candidates:
        assert cand.intraday_pattern in allowed


def test_mock_candidate_at_least_one_non_unknown_intraday_pattern():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    patterns = {c.intraday_pattern for c in candidates}
    assert patterns - {"unknown"}, f"mock should expose at least one real pattern, got: {patterns}"
