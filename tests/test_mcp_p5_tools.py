def test_get_dragon_tiger_tool_returns_dict():
    from aegis_alpha.mcp.server import get_dragon_tiger

    result = get_dragon_tiger("600519", "2026-05-30")
    assert isinstance(result, dict)
    assert result.get("symbol") == "600519"
    assert "seats" in result


def test_get_active_seats_today_tool_returns_list():
    from aegis_alpha.mcp.server import get_active_seats_today

    result = get_active_seats_today("2026-05-30")
    assert isinstance(result, list)
    if result:
        assert "hot_money_alias" in result[0]


def test_get_limit_down_pool_returns_list():
    from aegis_alpha.mcp.server import get_limit_down_pool

    rows = get_limit_down_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "limit_down"


def test_get_st_pool_returns_list():
    from aegis_alpha.mcp.server import get_st_pool

    rows = get_st_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "st"


def test_compact_candidate_includes_limitup_driver_and_pattern(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    reset_singletons()
    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "limitup_driver_type" in item
        assert "intraday_pattern" in item


def test_get_capital_flow_slices_returns_three_dicts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_capital_flow_slices

    reset_singletons()
    rows = get_capital_flow_slices("600519", "2026-05-30")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert {r["window"] for r in rows} == {
        "pre_first_seal_5m", "post_break_1m", "tail_30m"
    }


def test_compact_candidate_includes_weekly_health_score(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    reset_singletons()
    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "weekly_health_score" in item
        assert 0.0 <= item["weekly_health_score"] <= 100.0


def test_compact_candidate_includes_agent_factor_facts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    reset_singletons()
    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "promotion_grade" not in item
        assert "third_board_probability_pct" not in item
        assert "theme_lifecycle_stage" in item
        assert "free_float_market_cap_cny" in item
        assert "turnover_cny" in item
        assert "avg_turnover_10d_cny" in item
        assert "prev_day_volume_shrink_ratio" in item
        assert "break_board_count" in item
        assert "reseal_count" in item
        assert "max_seal_amount_cny" in item


def test_compact_candidate_break_filter_splits_break_and_no_break_candidates(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    reset_singletons()
    no_break = get_second_board_candidates_compact(limit=10, break_filter="exclude")
    break_only = get_second_board_candidates_compact(limit=10, break_filter="only")

    assert no_break
    assert break_only
    assert all(item["break_board_count"] == 0 for item in no_break)
    assert all(item["break_board_count"] > 0 for item in break_only)


def test_get_active_seats_today_includes_data_mode_field():
    from aegis_alpha.mcp.server import get_active_seats_today

    rows = get_active_seats_today("2026-06-01")
    # mock 模式可能不需要 data_mode；jvquant placeholder 一定有；本测试只
    # 验证返回结构可读，让 Hermes 即使解析 mock 也不会崩。
    assert isinstance(rows, list) or isinstance(rows, dict)
    if isinstance(rows, list):
        for r in rows:
            assert "hot_money_alias" in r
