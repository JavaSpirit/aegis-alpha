from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_explain_reports_theme_lifecycle_stage():
    a = MockMarketDataAdapter()
    for c in a.get_second_board_candidates():
        blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
        assert "题材阶段" in blob


def test_explain_lifecycle_has_no_judgment_words():
    a = MockMarketDataAdapter()
    for c in a.get_second_board_candidates():
        blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
        for word in ("买入", "卖出", "推荐", "应该", "看多", "看空"):
            assert word not in blob
