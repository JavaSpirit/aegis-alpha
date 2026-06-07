from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_explain_observations_mention_client_facts():
    a = MockMarketDataAdapter()
    c = a.get_second_board_candidates()[0]
    blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
    assert "流通市值" in blob
    assert "斜率" in blob
    assert "T-1量比" in blob
    assert "前期高点" in blob


def test_explain_has_no_judgment_words():
    a = MockMarketDataAdapter()
    c = a.get_second_board_candidates()[0]
    blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
    for word in ("买入", "卖出", "推荐", "应该", "强烈", "强", "弱", "好", "差", "看多", "看空"):
        assert word not in blob
