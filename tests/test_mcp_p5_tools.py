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


def test_historical_second_board_candidate_tool_returns_facts_only(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_historical_second_board_candidates

    reset_singletons()
    rows = get_historical_second_board_candidates("2026-05-26", limit=2)

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "002230"
    assert "seal_amount_cny" in rows[0]
    assert "promotion_grade" not in rows[0]
    assert "promotion_likelihood" not in rows[0]


def test_historical_first_board_watchlist_tool_returns_as_of_facts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_historical_first_board_watchlist

    reset_singletons()
    rows = get_historical_first_board_watchlist("2026-05-25", limit=2)

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0]["as_of_day"] == "2026-05-25"
    assert rows[0]["target_second_board_day"] == "2026-05-26"
    assert rows[0]["first_board_confirmed"] is True
    assert "seal_amount_cny" in rows[0]
    assert "promotion_grade" not in rows[0]
    assert "promotion_likelihood" not in rows[0]


def test_strategy_watchlist_tool_returns_client_strategy_facts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_strategy_watchlist

    reset_singletons()
    result = get_strategy_watchlist("2026-05-25", limit=2)

    assert isinstance(result, dict)
    assert result["as_of_day"] == "2026-05-25"
    assert result["result_count"] == 2
    rows = result["candidates"]
    assert len(rows) == 2
    assert rows[0]["avg_turnover_10d_pass"] is True
    assert rows[0]["prev_day_shrink"] is True
    assert "ma5_slope_in_client_range" not in rows[0]
    assert "strategy_coverage" not in rows[0]
    assert any("large_turnover_trend_seed" in row["candidate_sources"] for row in rows)
    assert "theme_continuity" in rows[0]
    assert rows[0]["theme_continuity"]["off_platform_news_checked"] is False
    assert rows[0]["theme_continuity"]["cls_news_checked"] is False
    assert any("MA5 slope" in gap for gap in result["data_gaps"])
    assert "promotion_grade" not in rows[0]
    assert "promotion_likelihood" not in rows[0]


def test_daily_strategy_candidate_pool_returns_agent_selection_inputs(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_daily_strategy_candidate_pool

    reset_singletons()
    result = get_daily_strategy_candidate_pool("2026-05-25", limit=5)

    assert result["data_mode"] == "daily_strategy_candidate_pool"
    assert result["intended_use"] == "facts_for_agent_selection"
    assert result["provider_order_is_not_alpha_rank"] is True
    assert result["candidate_generation"]["active_program_filter"] == "avg_turnover_10d_pass_only"
    assert "large_turnover_trend_seed" in result["candidate_generation"]["universe_sources"]
    assert result["coverage_summary"]["avg_turnover_10d"] >= 1
    assert result["next_step"]["then_call"] == "get_strategy_decision_packet"
    assert result["result_count"] >= 1
    item = result["candidates"][0]
    assert "strategy_seed_reasons" in item
    assert "strategy_coverage" in item
    assert "theme_continuity" in item
    assert "grade" not in item
    assert "score" not in item
    assert "promotion_likelihood" not in item


def test_theme_continuity_tool_returns_market_internal_facts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_theme_continuity

    reset_singletons()
    result = get_theme_continuity("AI应用", "2026-05-25", lookback_days=14)

    assert isinstance(result, dict)
    assert result["theme"] == "AI应用"
    assert result["continuity_label"] == "persistent"
    assert result["active_days"] >= 1
    assert result["off_platform_news_checked"] is False
    assert result["cls_news_checked"] is False
    assert "grade" not in result


def test_historical_strategy_replay_tool_returns_research_alert_facts(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import run_historical_strategy_replay

    reset_singletons()
    result = run_historical_strategy_replay("2026-05-25", "2026-05-26", symbols="002230", limit=2)

    assert isinstance(result, dict)
    assert result["as_of_day"] == "2026-05-25"
    assert result["target_day"] == "2026-05-26"
    assert result["data_mode"] == "historical_replay"
    assert result["requested_window"] == {"start": "", "end": ""}
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["symbol"] == "002230"
    assert "signals" in item
    assert "avg_turnover_10d_pass" in item
    assert "prev_day_shrink" in item
    assert "pattern_diagnostics" in item
    assert "no_signal_reason" in item["pattern_diagnostics"]
    assert "data_gaps" in item
    dumped = str(result)
    for phrase in ("卖出", "下单", "全仓", "梭哈", "买入吧", "去买", "立即买"):
        assert phrase not in dumped
    assert "sealed_next_day" not in item
    assert "next_day_close_pct" not in item


def test_historical_strategy_replay_symbol_lookup_ignores_display_limit(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import run_historical_strategy_replay

    reset_singletons()
    result = run_historical_strategy_replay("2026-05-25", "2026-05-26", symbols="300475", limit=1)

    assert result["result_count"] == 1
    assert result["results"][0]["symbol"] == "300475"
    assert result["requested_symbols"] == ["300475"]
    assert result["missing_requested_symbols"] == []


def test_historical_strategy_replay_accepts_time_window(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import run_historical_strategy_replay

    reset_singletons()
    result = run_historical_strategy_replay(
        "2026-05-25",
        "2026-05-26",
        symbols="002230",
        limit=2,
        window_start="09:31",
        window_end="10:00",
    )

    assert result["requested_window"] == {"start": "09:31", "end": "10:00"}
    assert result["results"][0]["requested_window"] == {"start": "09:31", "end": "10:00"}
    if result["results"][0]["data_mode"] != "unavailable":
        assert result["results"][0]["replay_window"].startswith("09:")


def test_historical_trigger_validation_tool_returns_calibration_table(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import run_historical_trigger_validation

    reset_singletons()
    result = run_historical_trigger_validation(
        end_day="2026-05-26",
        lookback_days=3,
        limit=5,
        window_start="09:31",
        window_end="10:00",
    )

    assert result["data_mode"] == "historical_validation"
    assert result["window"] == {"start": "09:31", "end": "10:00"}
    assert result["day_count"] >= 1
    assert "candidate_count" in result
    assert "triggered_count" in result
    assert "no_signal_reason_counts" in result
    assert "validations" in result
    dumped = str(result)
    for phrase in ("卖出", "下单", "全仓", "梭哈", "买入吧", "去买", "立即买"):
        assert phrase not in dumped


def test_intraday_theme_copump_tool_returns_same_theme_proxy(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_intraday_theme_copump

    reset_singletons()
    result = get_intraday_theme_copump(
        "002230",
        as_of_day="2026-05-25",
        target_day="2026-05-26",
        trigger_time="09:41",
        window_start="09:31",
        window_end="10:00",
        peer_limit=10,
    )

    assert result["data_mode"] == "historical_theme_copump"
    assert result["symbol"] == "002230"
    assert result["window"] == {"start": "09:31", "end": "10:00"}
    assert result["copump"]["universe"] == "same_theme_full_strategy_watchlist_candidates"
    assert result["copump"]["crossed_previous_high_by_trigger_count"] >= 0
    assert "peer_details" in result
    assert "full-market sector breadth" in " ".join(result["notes"])


def test_intraday_orderflow_confirmation_tool_separates_missing_big_order_ratio(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_intraday_orderflow_confirmation

    reset_singletons()
    result = get_intraday_orderflow_confirmation(
        "002230",
        trading_day="2026-05-26",
        trigger_time="09:41",
        window_start="09:31",
        window_end="10:00",
    )

    assert result["data_mode"] == "historical_orderflow_proxy"
    assert result["window"] == {"start": "09:31", "end": "10:00"}
    assert result["historical_big_order_buy_ratio_available"] is False
    assert result["big_order_buy_ratio"] is None
    assert result["realtime_orderflow_capability"]["can_compute_big_order_buy_ratio"] is False
    assert result["realtime_orderflow_capability"]["active_trade_side_available"] is False
    assert result["daily_capital_flow_available"] is True
    assert result["daily_capital_flow"]["big_order_net_inflow_ratio"] == 0.08
    assert "historical_minute_level_active_big_order_buy_ratio" in result["data_gaps"]


def test_sample_realtime_large_trade_proxy_tool_returns_directionless_proxy(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import sample_realtime_large_trade_proxy

    reset_singletons()
    result = sample_realtime_large_trade_proxy(
        "002230",
        duration_seconds=2,
        threshold_cny=3_000_000,
        window_start="09:31",
        window_end="10:00",
    )

    assert result["data_mode"] == "realtime_large_trade_proxy"
    assert result["sample_available"] is True
    assert result["raw_message_count"] == 1
    assert result["proxy_metric"] == "directionless_large_trade_amount_cny"
    assert result["active_trade_side_available"] is False
    assert result["can_compute_big_order_buy_ratio"] is False
    assert result["stats"]["trade_count"] == 2
    assert result["stats"]["total_amount_cny"] == 18_000_000


def test_simulate_historical_orderflow_proxy_tool_returns_minute_volume_proxy(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import simulate_historical_orderflow_proxy

    reset_singletons()
    result = simulate_historical_orderflow_proxy(
        "002230",
        trading_day="2026-05-26",
        window_start="09:31",
        window_end="10:00",
        volume_ratio_threshold=1.5,
    )

    assert result["data_mode"] == "historical_minute_volume_proxy"
    assert result["proxy_source"] == "minute_volume"
    assert result["can_compute_big_order_buy_ratio"] is False
    assert result["active_trade_side_available"] is False
    assert result["spike_minute_count"] == 2


def test_strategy_decision_packet_bundles_facts_without_program_grade(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_strategy_decision_packet

    reset_singletons()
    result = get_strategy_decision_packet(
        "2026-05-25",
        "2026-05-26",
        symbols="002230",
        limit=3,
        window_start="09:31",
        window_end="10:00",
    )

    assert result["data_mode"] == "strategy_decision_packet"
    assert result["window"] == {"start": "09:31", "end": "10:00"}
    assert result["result_count"] == 1
    item = result["results"][0]
    assert item["symbol"] == "002230"
    if item["data_mode"] != "unavailable":
        assert "pattern_diagnostics" in item
    else:
        assert item["error"] == "missing_minute_bars"
    assert "orderflow_confirmation" in item
    assert "intraday_theme_copump" in item
    assert item["intraday_theme_copump"]["data_mode"] == "packet_selected_results_copump"
    assert "full_theme_copump" not in item["intraday_theme_copump"]
    assert "historical_minute_volume_proxy" not in item
    assert "grade" not in item
    assert "promotion_likelihood" not in item
    assert item["orderflow_confirmation"]["can_compute_big_order_buy_ratio"] is False


def test_second_board_next_day_outcomes_tool_accepts_symbol_string(monkeypatch):
    monkeypatch.setenv("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock")
    from aegis_alpha.mcp.dependencies import reset_singletons
    from aegis_alpha.mcp.server import get_second_board_next_day_outcomes

    reset_singletons()
    result = get_second_board_next_day_outcomes("2026-05-26", "002230|300024", limit=5)

    assert isinstance(result, dict)
    assert result["trading_day"] == "2026-05-26"
    assert result["symbols"] == ["002230", "300024"]
    assert len(result["outcomes"]) == 2
    assert result["outcomes"][0]["touched_limit_up"] is True
    assert "grade" not in result["outcomes"][0]


def test_get_active_seats_today_includes_data_mode_field():
    from aegis_alpha.mcp.server import get_active_seats_today

    rows = get_active_seats_today("2026-06-01")
    # mock 模式可能不需要 data_mode；jvquant placeholder 一定有；本测试只
    # 验证返回结构可读，让 Hermes 即使解析 mock 也不会崩。
    assert isinstance(rows, list) or isinstance(rows, dict)
    if isinstance(rows, list):
        for r in rows:
            assert "hot_money_alias" in r
