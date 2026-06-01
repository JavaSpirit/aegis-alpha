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
