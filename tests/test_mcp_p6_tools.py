def test_find_similar_setups_tool_returns_list():
    from aegis_alpha.mcp.server import find_similar_setups

    result = find_similar_setups("600519", 90, 0.5)
    assert isinstance(result, list) or isinstance(result, dict)


def test_find_similar_setups_rejects_empty_symbol():
    from aegis_alpha.mcp.server import find_similar_setups

    res = find_similar_setups("", 90, 0.5)
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"


def test_get_new_stock_candidates_returns_list():
    from aegis_alpha.mcp.server import get_new_stock_candidates

    out = get_new_stock_candidates()
    assert isinstance(out, list)
    if out:
        item = out[0]
        assert "symbol" in item and "tier" in item


def test_get_suspended_stocks_returns_list():
    from aegis_alpha.mcp.server import get_suspended_stocks

    out = get_suspended_stocks("2026-06-01")
    assert isinstance(out, list)
    if out:
        assert "symbol" in out[0]
        assert "suspension_start_day" in out[0]


def test_query_minute_bars_returns_list_or_unavailable_dict():
    from aegis_alpha.mcp.server import query_minute_bars

    res = query_minute_bars("600519", "2026-06-01", "2026-06-01")
    if isinstance(res, dict):
        assert res.get("data_mode") == "unavailable"
    else:
        assert isinstance(res, list)


def test_query_minute_bars_rejects_empty_args():
    from aegis_alpha.mcp.server import query_minute_bars

    res = query_minute_bars("", "2026-06-01", "2026-06-01")
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"


def test_simulate_outcome_rejects_empty_args():
    from aegis_alpha.mcp.server import simulate_outcome

    res = simulate_outcome("", "2026-05-30", "{}")
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"


def test_simulate_outcome_returns_unavailable_when_no_snapshot():
    from aegis_alpha.mcp.server import simulate_outcome

    res = simulate_outcome("ZZZ", "2026-05-30", "{}")
    assert isinstance(res, dict)
    # 当快照不存在时也走 unavailable 分支
    assert res.get("data_mode") == "unavailable"
