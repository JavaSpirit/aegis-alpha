from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Callable

from aegis_alpha.adapters.jvquant import parsers as P
from aegis_alpha.adapters.jvquant.data_quality import build_second_board_data_quality
from aegis_alpha.adapters.jvquant.scoring import (
    candidate_grade,
    candidate_grade_reason,
    estimated_seal_probability,
    theme_position_label,
    third_board_promotion_assessment,
)
from aegis_alpha.clock import SH_TZ
from aegis_alpha.grading import CandidateGradingConfig
from aegis_alpha.models import (
    HistoryStats,
    LadderEntry,
    MinuteReplaySnapshot,
    SecondBoardCandidate,
    SignalMetadata,
    StockOrderbookSnapshot,
    ThemeLeader,
    ThemeLeaderRole,
)
from aegis_alpha.extensions.limitup_driver import (
    LimitupDriverInputs,
    classify_limitup_driver,
)
from aegis_alpha.extensions.intraday_pattern import (
    PatternInputs,
    classify_intraday_pattern,
)
from aegis_alpha.symbols import daily_limit_pct
from aegis_alpha.themes.auction import AuctionAnalyzer


def _inferred_change_pct(symbol: str) -> float:
    return daily_limit_pct(symbol)


def build_one_candidate(
    *,
    index: int,
    row: dict[str, Any],
    seal_rows: dict[str, dict[str, Any]],
    speed_1m_rows: dict[str, dict[str, Any]],
    speed_3m_rows: dict[str, dict[str, Any]],
    speed_10m_rows: dict[str, dict[str, Any]],
    auction_rows: dict[str, dict[str, Any]],
    theme_rows: dict[str, dict[str, Any]],
    break_reseal_rows: dict[str, dict[str, Any]],
    max_seal_rows: dict[str, dict[str, Any]],
    query_timestamp: str,
    theme_counts: Counter,
    gate_action: str,
    orderbook_limit: int,
    minute_replay_enabled: bool,
    minute_replay_limit: int,
    grading_config: CandidateGradingConfig,
    get_minute_replay: Callable[[str], MinuteReplaySnapshot],
    get_orderbook: Callable[[str], StockOrderbookSnapshot],
    ladder_entries: dict[str, LadderEntry],
    theme_leaders_by_theme: dict[str, ThemeLeader],
    history_stats_by_symbol: dict[str, HistoryStats],
    theme_board_profiles: dict[str, dict[str, Any]],
    weekly_health_score: float = 50.0,
) -> SecondBoardCandidate:
    symbol = P._symbol_from_row(row)
    seal_row = seal_rows.get(symbol, {})
    speed_1m_row = speed_1m_rows.get(symbol, {})
    speed_3m_row = speed_3m_rows.get(symbol, {})
    speed_10m_row = speed_10m_rows.get(symbol, {})
    auction_row = auction_rows.get(symbol, {})
    theme_row = theme_rows.get(symbol, {})
    break_reseal_row = break_reseal_rows.get(symbol, {})
    max_seal_row = max_seal_rows.get(symbol, {})
    change_pct = P.float_or_zero(
        P._first_field_value(
            [row, seal_row, break_reseal_row, theme_row, max_seal_row],
            "涨跌幅",
        )
    )
    speed_field, speed_value = P._field_entry(row, "涨速", "区间涨跌幅")
    five_min_speed_pct = P.float_or_zero(speed_value)
    speed_window, speed_timestamp, has_exact_speed_window = P._speed_window_from_field(
        speed_field,
        query_timestamp,
    )
    one_min_speed_pct, one_min_speed_window, one_min_speed_timestamp, has_exact_1m_window = (
        P._speed_from_row(speed_1m_row, query_timestamp)
    )
    three_min_speed_pct, three_min_speed_window, three_min_speed_timestamp, has_exact_3m_window = (
        P._speed_from_row(speed_3m_row, query_timestamp)
    )
    ten_min_speed_pct, ten_min_speed_window, ten_min_speed_timestamp, has_exact_10m_window = (
        P._speed_from_row(speed_10m_row, query_timestamp)
    )
    minute_replay_timestamp = ""
    minute_replay_trading_day = ""
    minute_replay_bar_count = 0
    minute_replay_notes: list[str] = []
    minute_replay_used = False
    if minute_replay_enabled and index < minute_replay_limit:
        try:
            minute_replay = get_minute_replay(symbol)
            minute_replay_timestamp = minute_replay.timestamp
            minute_replay_trading_day = minute_replay.trading_day
            minute_replay_bar_count = minute_replay.minute_count
            if minute_replay.minute_count >= 2 and minute_replay.speed_pct_by_window:
                one_min_speed_pct = minute_replay.speed_pct_by_window.get("1m", one_min_speed_pct)
                three_min_speed_pct = minute_replay.speed_pct_by_window.get("3m", three_min_speed_pct)
                five_min_speed_pct = minute_replay.speed_pct_by_window.get("5m", five_min_speed_pct)
                ten_min_speed_pct = minute_replay.speed_pct_by_window.get("10m", ten_min_speed_pct)
                one_min_speed_window = minute_replay.speed_window_by_window.get("1m", one_min_speed_window)
                three_min_speed_window = minute_replay.speed_window_by_window.get("3m", three_min_speed_window)
                speed_window = minute_replay.speed_window_by_window.get("5m", speed_window)
                ten_min_speed_window = minute_replay.speed_window_by_window.get("10m", ten_min_speed_window)
                one_min_speed_timestamp = minute_replay.timestamp
                three_min_speed_timestamp = minute_replay.timestamp
                speed_timestamp = minute_replay.timestamp
                ten_min_speed_timestamp = minute_replay.timestamp
                has_exact_speed_window = True
                has_exact_1m_window = True
                has_exact_3m_window = True
                has_exact_10m_window = True
                minute_replay_used = True
            minute_replay_notes.extend(minute_replay.notes)
        except Exception as exc:
            minute_replay_notes.append(f"minute_replay_unavailable={type(exc).__name__}")
    turnover_cny = P._parse_cny_amount(P._field_value(row, "成交额"))
    free_float_market_cap_cny = P._parse_cny_amount(P._field_value(row, "流通市值"))
    main_net_inflow_cny = P._parse_cny_amount(
        P._field_value(row, "主力净额", "大单净额", "超大单净额")
    )
    big_order_net_inflow_ratio = P._ratio(main_net_inflow_cny, turnover_cny)
    first_limit_up_time = P._time_or_unknown(
        P._field_value(seal_row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
    )
    seal_amount_cny = P._parse_cny_amount(P._field_value(seal_row, "涨停封单额", "封单金额", "封单额"))
    seal_volume_shares = P._parse_share_amount(
        P._field_value(seal_row, "涨停封单量", "封单量", "封单量(股)")
    )
    seal_to_turnover_ratio = P.float_or_zero(P._field_value(seal_row, "涨停封成比", "封成比"))
    change_pct_inferred = False
    if change_pct == 0 and (first_limit_up_time != "unknown" or seal_amount_cny > 0):
        change_pct = _inferred_change_pct(symbol)
        change_pct_inferred = True
    auction_change_pct = P.float_or_zero(P._field_value(auction_row, "集合竞价涨跌幅", "竞价涨幅"))
    auction_turnover_cny = P._parse_cny_amount(P._field_value(auction_row, "集合竞价成交额", "竞价成交额"))
    auction_turnover_rate = P.float_or_zero(P._field_value(auction_row, "集合竞价换手率", "竞价换手率"))
    auction_analysis = AuctionAnalyzer().analyze(
        symbol=symbol,
        trading_day=datetime.now(SH_TZ).date().isoformat(),
        auction_change_pct=auction_change_pct,
        auction_turnover_cny=auction_turnover_cny,
        auction_turnover_rate=auction_turnover_rate,
    )
    concept_tags = P._tags_from_row(theme_row, "概念", "所属概念")
    topic_tags = P._tags_from_row(theme_row, "个股题材", "题材")
    break_board_count = P.int_or_zero(P._field_value(break_reseal_row, "炸板次数", "炸板次数(次)"))
    reseal_count = P.int_or_zero(P._field_value(break_reseal_row, "涨停回封次数", "回封次数"))
    final_seal_time = P._time_or_unknown(
        P._field_value(break_reseal_row, "涨停最终封板时间", "最后封板时间", "最终封板时间")
    )
    max_seal_amount_cny = P._parse_cny_amount(
        P._field_value(max_seal_row, "最大封单金额", "涨停封单额", "封单金额")
    )
    max_seal_volume_shares = P._parse_share_amount(
        P._field_value(max_seal_row, "最大封单量", "涨停封单量", "封单量")
    )
    theme = P._theme_from_row(row)

    ladder = ladder_entries.get(symbol)
    previous_consecutive = ladder.consecutive_boards if ladder else 0
    previous_height = ladder.height_label if ladder else "unknown"
    theme_profile = theme_board_profiles.get(theme, {})
    theme_max_height = int(theme_profile.get("max_height", previous_consecutive or 0))
    theme_multi_board_count = int(theme_profile.get("multi_board_count", theme_counts[theme]))
    theme_recent_active_days = int(theme_profile.get("recent_active_days", 0))
    theme_recent_max_member_count = int(theme_profile.get("recent_max_member_count", 0))
    theme_position = theme_position_label(
        theme_max_height=theme_max_height,
        theme_multi_board_count=theme_multi_board_count,
    )
    lifecycle_stage = str(theme_profile.get("lifecycle_stage", "unknown"))
    stage_order = {"unknown": 0, "early": 1, "maturing": 2, "extended": 3}
    if stage_order.get(lifecycle_stage, 0) > stage_order.get(theme_position, 0):
        theme_position = lifecycle_stage

    limitup_driver_type = classify_limitup_driver(
        LimitupDriverInputs(
            symbol=symbol,
            concept_tags=list(concept_tags),
            topic_tags=list(topic_tags),
            list_reason="",
            net_amount_cny=0.0,
            previous_consecutive_boards=int(previous_consecutive or 0),
        )
    )

    leader = theme_leaders_by_theme.get(theme)
    theme_role: ThemeLeaderRole = "unknown"
    theme_leader_symbol = ""
    if leader is not None:
        theme_leader_symbol = leader.leader_symbol
        if symbol == leader.leader_symbol:
            theme_role = "leader"
        elif symbol in leader.co_leader_symbols:
            theme_role = "co_leader"
        else:
            theme_role = "follower"

    orderbook_quality = 50.0
    orderbook_notes: list[str] = []
    orderbook_timestamp = query_timestamp
    orderbook_has_rows = False
    queue_position_note = "Own-order queue position unavailable; no live order has been placed or tracked."
    if index < orderbook_limit:
        try:
            orderbook = get_orderbook(symbol)
            orderbook_timestamp = orderbook.timestamp
            bid_volume = sum(level.volume_count for level in orderbook.bid_levels)
            ask_volume = sum(level.volume_count for level in orderbook.ask_levels)
            total_volume = bid_volume + ask_volume
            orderbook_has_rows = bool(total_volume)
            if total_volume:
                orderbook_quality = round(100 * bid_volume / total_volume, 2)
            if orderbook.best_bid_price is None and orderbook.best_ask_price is None:
                queue_position_note = (
                    "Orderbook queue unavailable from provider; own-order queue position cannot be inferred."
                )
                orderbook_notes.append("jvQuant orderbook returned no queue rows for this candidate.")
            else:
                queue_position_note = P._queue_position_note(orderbook)
                orderbook_notes.append(
                    f"jvQuant orderbook best_bid={orderbook.best_bid_price}, best_ask={orderbook.best_ask_price}."
                )
        except Exception as exc:
            queue_position_note = (
                "Orderbook queue unavailable because provider request failed; "
                "own-order queue position cannot be inferred."
            )
            orderbook_notes.append(f"Orderbook unavailable for candidate scoring: {type(exc).__name__}.")

    _stats = history_stats_by_symbol.get(symbol)
    three_year_touch_rate = _stats.touch_limit_up_success_rate if _stats is not None else 0.0
    three_year_gap_up_rate = _stats.sealed_next_day_gap_up_rate if _stats is not None else 0.0

    intraday_pattern_value = "unknown"
    if minute_replay_used and minute_replay.previous_close > 0:
        daily_limit_value = daily_limit_pct(symbol)
        limit_price_threshold = minute_replay.previous_close * (1.0 + daily_limit_value / 100.0)
        pattern_bars: list[dict] = []
        for bar in minute_replay.bars:
            try:
                hh, mm, *_ = bar.time.split(":")
                minute_offset = max(0, (int(hh) - 9) * 60 + int(mm) - 30)
            except Exception:
                continue
            change_pct_local = (
                (bar.last_price - minute_replay.previous_close)
                / minute_replay.previous_close
                * 100.0
            )
            at_limit = bar.last_price >= limit_price_threshold - 0.005
            pattern_bars.append({
                "minute": minute_offset,
                "change_pct": float(change_pct_local),
                "at_limit": bool(at_limit),
            })

        first_seal_minute = 0
        if first_limit_up_time and first_limit_up_time != "unknown":
            try:
                hh, mm = first_limit_up_time.split(":")[:2]
                first_seal_minute = max(0, (int(hh) - 9) * 60 + int(mm) - 30)
            except Exception:
                first_seal_minute = 0
        sealed_at_open = first_seal_minute <= 1
        closed_at_limit = abs(float(change_pct) - daily_limit_value) < 0.05
        features = classify_intraday_pattern(
            PatternInputs(
                bars=pattern_bars,
                daily_limit_pct=daily_limit_value,
                break_count=int(break_board_count or 0),
                reseal_count=int(reseal_count or 0),
                first_seal_minute=first_seal_minute,
                sealed_at_open=sealed_at_open,
                closed_at_limit=closed_at_limit,
            )
        )
        intraday_pattern_value = features.pattern

    grade = candidate_grade(
        action=gate_action,
        change_pct=change_pct,
        five_min_speed_pct=five_min_speed_pct,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        orderbook_quality=orderbook_quality,
        theme_count=theme_counts[theme],
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        config=grading_config,
    )
    estimated = estimated_seal_probability(
        action=gate_action,
        change_pct=change_pct,
        five_min_speed_pct=five_min_speed_pct,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        orderbook_quality=orderbook_quality,
        theme_count=theme_counts[theme],
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        config=grading_config,
    )
    promotion = third_board_promotion_assessment(
        action=gate_action,
        theme_role=theme_role,
        theme_position=theme_position,
        theme_max_height=theme_max_height,
        theme_multi_board_count=theme_multi_board_count,
        theme_recent_active_days=theme_recent_active_days,
        theme_recent_max_member_count=theme_recent_max_member_count,
        free_float_market_cap_cny=free_float_market_cap_cny,
        turnover_cny=turnover_cny,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        first_limit_up_time=first_limit_up_time,
        break_board_count=break_board_count,
        reseal_count=reseal_count,
        final_seal_time=final_seal_time,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        orderbook_quality=orderbook_quality,
        auction_change_pct=auction_change_pct,
        auction_turnover_cny=auction_turnover_cny,
        weekly_health_score=weekly_health_score,
        config=grading_config,
    )
    grade_reason = candidate_grade_reason(
        action=gate_action,
        grade=grade,
        change_pct=change_pct,
        five_min_speed_pct=five_min_speed_pct,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        orderbook_quality=orderbook_quality,
        theme_count=theme_counts[theme],
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        queue_position_note=queue_position_note,
        limitup_driver_type=limitup_driver_type,
        intraday_pattern=intraday_pattern_value,
    )
    data_quality = build_second_board_data_quality(
        speed_timestamp=speed_timestamp,
        speed_window=speed_window,
        has_exact_speed_window=has_exact_speed_window,
        has_exact_multi_speed_windows=has_exact_1m_window or has_exact_3m_window or has_exact_10m_window,
        query_timestamp=query_timestamp,
        has_capital_flow=main_net_inflow_cny != 0,
        has_auction_data=bool(auction_row),
        has_theme_tags=bool(concept_tags or topic_tags),
        has_break_reseal_data=bool(break_reseal_row),
        has_max_seal_data=max_seal_amount_cny > 0 or max_seal_volume_shares > 0,
        has_seal_data=first_limit_up_time != "unknown" or seal_amount_cny > 0 or seal_volume_shares > 0,
        has_orderbook_rows=orderbook_has_rows,
        orderbook_timestamp=orderbook_timestamp,
        minute_replay_used=minute_replay_used,
        minute_replay_timestamp=minute_replay_timestamp,
        minute_replay_bar_count=minute_replay_bar_count,
    )

    return build_second_board_candidate(
        symbol=symbol,
        name=P._name_from_row(row),
        theme=theme,
        previous_consecutive_boards=previous_consecutive,
        previous_height_label=previous_height,
        theme_role=theme_role,
        theme_leader_symbol=theme_leader_symbol,
        change_pct=change_pct,
        change_pct_inferred=change_pct_inferred,
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_volume_shares=seal_volume_shares,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        queue_position_note=queue_position_note,
        auction_change_pct=auction_change_pct,
        auction_turnover_cny=auction_turnover_cny,
        auction_turnover_rate=auction_turnover_rate,
        auction_pattern=auction_analysis.pattern,
        five_min_speed_pct=five_min_speed_pct,
        speed_window=speed_window,
        speed_timestamp=speed_timestamp,
        minute_replay_timestamp=minute_replay_timestamp,
        minute_replay_trading_day=minute_replay_trading_day,
        minute_replay_bar_count=minute_replay_bar_count,
        minute_replay_used=minute_replay_used,
        one_min_speed_pct=one_min_speed_pct,
        one_min_speed_window=one_min_speed_window,
        one_min_speed_timestamp=one_min_speed_timestamp,
        three_min_speed_pct=three_min_speed_pct,
        three_min_speed_window=three_min_speed_window,
        three_min_speed_timestamp=three_min_speed_timestamp,
        ten_min_speed_pct=ten_min_speed_pct,
        ten_min_speed_window=ten_min_speed_window,
        ten_min_speed_timestamp=ten_min_speed_timestamp,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        concept_tags=concept_tags,
        topic_tags=topic_tags,
        break_board_count=break_board_count,
        reseal_count=reseal_count,
        final_seal_time=final_seal_time,
        max_seal_amount_cny=max_seal_amount_cny,
        max_seal_volume_shares=max_seal_volume_shares,
        same_theme_rising_count=theme_counts[theme],
        orderbook_quality=orderbook_quality,
        three_year_touch_limit_success_rate=three_year_touch_rate,
        three_year_sealed_next_day_gap_up_rate=three_year_gap_up_rate,
        estimated=estimated,
        grade=grade,
        promotion_grade=str(promotion["promotion_grade"]),
        third_board_probability_pct=float(promotion["third_board_probability_pct"]),
        third_board_promotion_score=float(promotion["promotion_score"]),
        promotion_reason=str(promotion["promotion_reason"]),
        theme_position_label=theme_position,
        theme_max_height=theme_max_height,
        theme_multi_board_count=theme_multi_board_count,
        theme_recent_active_days=theme_recent_active_days,
        theme_recent_max_member_count=theme_recent_max_member_count,
        free_float_market_cap_cny=free_float_market_cap_cny,
        limitup_driver_type=limitup_driver_type,
        grade_reason=grade_reason,
        intraday_pattern=intraday_pattern_value,
        weekly_health_score=weekly_health_score,
        data_quality=data_quality,
        orderbook_notes=orderbook_notes,
        minute_replay_notes=minute_replay_notes,
        turnover_cny=turnover_cny,
        main_net_inflow_cny=main_net_inflow_cny,
    )


def build_second_board_candidate(
    *,
    symbol: str,
    name: str,
    theme: str,
    previous_consecutive_boards: int = 0,
    previous_height_label: str = "unknown",
    theme_role: ThemeLeaderRole = "unknown",
    theme_leader_symbol: str = "",
    change_pct: float,
    change_pct_inferred: bool,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_volume_shares: float,
    seal_to_turnover_ratio: float,
    queue_position_note: str,
    auction_change_pct: float,
    auction_turnover_cny: float,
    auction_turnover_rate: float,
    auction_pattern: str,
    five_min_speed_pct: float,
    speed_window: str,
    speed_timestamp: str,
    minute_replay_timestamp: str,
    minute_replay_trading_day: str,
    minute_replay_bar_count: int,
    minute_replay_used: bool,
    one_min_speed_pct: float,
    one_min_speed_window: str,
    one_min_speed_timestamp: str,
    three_min_speed_pct: float,
    three_min_speed_window: str,
    three_min_speed_timestamp: str,
    ten_min_speed_pct: float,
    ten_min_speed_window: str,
    ten_min_speed_timestamp: str,
    big_order_net_inflow_ratio: float,
    concept_tags: list[str],
    topic_tags: list[str],
    break_board_count: int,
    reseal_count: int,
    final_seal_time: str,
    max_seal_amount_cny: float,
    max_seal_volume_shares: float,
    same_theme_rising_count: int,
    orderbook_quality: float,
    three_year_touch_limit_success_rate: float,
    three_year_sealed_next_day_gap_up_rate: float,
    estimated: float,
    grade: str,
    promotion_grade: str = "C",
    third_board_probability_pct: float = 0.0,
    third_board_promotion_score: float = 0.0,
    promotion_reason: str = "",
    theme_position_label: str = "unknown",
    theme_max_height: int = 0,
    theme_multi_board_count: int = 0,
    theme_recent_active_days: int = 0,
    theme_recent_max_member_count: int = 0,
    free_float_market_cap_cny: float = 0.0,
    limitup_driver_type: str = "unknown",
    intraday_pattern: str = "unknown",
    weekly_health_score: float = 50.0,
    grade_reason: str = "",
    data_quality: dict[str, SignalMetadata] | None = None,
    orderbook_notes: list[str] | None = None,
    minute_replay_notes: list[str] | None = None,
    turnover_cny: float = 0.0,
    main_net_inflow_cny: float = 0.0,
) -> SecondBoardCandidate:
    if data_quality is None:
        data_quality = {}
    if orderbook_notes is None:
        orderbook_notes = []
    if minute_replay_notes is None:
        minute_replay_notes = []
    notes: list[str] = [
        "jvQuant live-provider candidate: strict second-board row with current limit-up and consecutive_boards=2.",
        (
            f"current_change_pct was inferred as {change_pct:.1f} from symbol board because jvQuant omitted the raw change field while seal metrics were present."
            if change_pct_inferred
            else "current_change_pct comes from a jvQuant semantic field."
        ),
        (
            "five_min_speed_pct comes from jvQuant minute replay bars recalculated by Aegis Alpha."
            if minute_replay_used
            else "five_min_speed_pct comes from a jvQuant semantic interval field; use five_min_speed_window for its time meaning."
        ),
        (
            "minute replay was used to recalculate 1m/3m/5m/10m speed windows."
            if minute_replay_used
            else "minute replay was unavailable or disabled; speed fields use jvQuant semantic query values."
        ),
        "capital-flow ratio comes from jvQuant semantic fields, not tick-by-tick trade classification.",
        "three_year_* rates derived from compute_history_stats over stored review_outcomes.",
        f"five_min_speed_window={speed_window}",
        f"five_min_speed_timestamp={speed_timestamp}",
        f"minute_replay_timestamp={minute_replay_timestamp}",
        f"minute_replay_trading_day={minute_replay_trading_day}",
        f"minute_replay_bar_count={minute_replay_bar_count}",
        f"one_min_speed_pct={one_min_speed_pct:.2f}",
        f"three_min_speed_pct={three_min_speed_pct:.2f}",
        f"ten_min_speed_pct={ten_min_speed_pct:.2f}",
        f"auction_change_pct={auction_change_pct:.2f}",
        f"auction_turnover_cny={auction_turnover_cny:.0f}",
        f"auction_turnover_rate={auction_turnover_rate:.2f}",
        f"concept_tags={','.join(concept_tags[:5])}",
        f"topic_tags={','.join(topic_tags[:5])}",
        f"break_board_count={break_board_count}",
        f"reseal_count={reseal_count}",
        f"final_seal_time={final_seal_time}",
        f"max_seal_amount_cny={max_seal_amount_cny:.0f}",
        f"first_limit_up_time={first_limit_up_time}",
        f"seal_amount_cny={seal_amount_cny:.0f}",
        f"seal_volume_shares={seal_volume_shares:.0f}",
        f"seal_to_turnover_ratio={seal_to_turnover_ratio:.2f}",
        f"queue_position_note={queue_position_note}",
        f"turnover_cny={turnover_cny:.0f}",
        f"main_net_inflow_cny={main_net_inflow_cny:.0f}",
        f"free_float_market_cap_cny={free_float_market_cap_cny:.0f}",
        f"theme_position_label={theme_position_label}",
        f"theme_max_height={theme_max_height}",
        f"theme_multi_board_count={theme_multi_board_count}",
        f"theme_recent_active_days={theme_recent_active_days}",
        f"theme_recent_max_member_count={theme_recent_max_member_count}",
        f"promotion_grade={promotion_grade}",
        f"third_board_probability_pct={third_board_probability_pct:.2f}",
        f"third_board_promotion_score={third_board_promotion_score:.2f}",
        f"promotion_reason={promotion_reason}",
        *orderbook_notes,
        *minute_replay_notes[:5],
    ]

    return SecondBoardCandidate(
        symbol=symbol,
        name=name,
        data_mode="live_provider",
        provider="jvQuant",
        theme=theme,
        previous_limit_up_time="unknown",
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_volume_shares=seal_volume_shares,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        queue_position_note=queue_position_note,
        current_change_pct=change_pct,
        auction_change_pct=auction_change_pct,
        auction_turnover_cny=auction_turnover_cny,
        auction_turnover_rate=auction_turnover_rate,
        previous_consecutive_boards=previous_consecutive_boards,
        previous_height_label=previous_height_label,
        theme_role=theme_role,
        theme_leader_symbol=theme_leader_symbol,
        auction_pattern=auction_pattern,
        five_min_speed_pct=five_min_speed_pct,
        five_min_speed_window=speed_window,
        five_min_speed_timestamp=speed_timestamp,
        minute_replay_timestamp=minute_replay_timestamp,
        minute_replay_trading_day=minute_replay_trading_day,
        minute_replay_bar_count=minute_replay_bar_count,
        one_min_speed_pct=one_min_speed_pct,
        one_min_speed_window=one_min_speed_window,
        one_min_speed_timestamp=one_min_speed_timestamp,
        three_min_speed_pct=three_min_speed_pct,
        three_min_speed_window=three_min_speed_window,
        three_min_speed_timestamp=three_min_speed_timestamp,
        ten_min_speed_pct=ten_min_speed_pct,
        ten_min_speed_window=ten_min_speed_window,
        ten_min_speed_timestamp=ten_min_speed_timestamp,
        big_order_net_inflow_ratio=big_order_net_inflow_ratio,
        concept_tags=concept_tags,
        topic_tags=topic_tags,
        break_board_count=break_board_count,
        reseal_count=reseal_count,
        final_seal_time=final_seal_time,
        max_seal_amount_cny=max_seal_amount_cny,
        max_seal_volume_shares=max_seal_volume_shares,
        same_theme_rising_count=same_theme_rising_count,
        orderbook_quality_score=orderbook_quality,
        three_year_touch_limit_success_rate=three_year_touch_limit_success_rate,
        three_year_sealed_next_day_gap_up_rate=three_year_sealed_next_day_gap_up_rate,
        estimated_seal_probability=estimated,
        grade=grade,
        promotion_grade=promotion_grade,
        third_board_probability_pct=third_board_probability_pct,
        third_board_promotion_score=third_board_promotion_score,
        promotion_reason=promotion_reason,
        theme_position_label=theme_position_label,
        theme_max_height=theme_max_height,
        theme_multi_board_count=theme_multi_board_count,
        theme_recent_active_days=theme_recent_active_days,
        theme_recent_max_member_count=theme_recent_max_member_count,
        free_float_market_cap_cny=free_float_market_cap_cny,
        turnover_cny=turnover_cny,
        main_net_inflow_cny=main_net_inflow_cny,
        limitup_driver_type=limitup_driver_type,
        intraday_pattern=intraday_pattern,
        weekly_health_score=weekly_health_score,
        grade_reason=grade_reason,
        data_quality=data_quality,
        notes=notes,
    )
