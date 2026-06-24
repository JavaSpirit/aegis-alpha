from __future__ import annotations

import re
from typing import Any

from aegis_alpha.adapters.jvquant import parsers as P
from aegis_alpha.measurements.client_facts import (
    avg_turnover_10d,
    broke_previous_high,
    prev_day_volume_shrink_ratio,
)
from aegis_alpha.symbols import daily_limit_pct, normalize_symbol


def historical_candidate_query(trading_day: str, prev_day: str) -> str:
    return (
        f"是否涨停@{prev_day},涨跌幅@{trading_day}大于5,非ST,"
        f"股票代码,股票简称,涨跌幅@{trading_day},"
        f"涨停首次封板时间@{trading_day},涨停封单额@{trading_day},"
        f"涨停封单量@{trading_day},涨停封成比@{trading_day},"
        f"收盘价@{trading_day},成交额@{trading_day},行业"
    )


def historical_first_board_watchlist_query(as_of_day: str, prev_day: str) -> str:
    return (
        f"是否涨停@{as_of_day},非ST,"
        f"股票代码,股票简称,涨跌幅@{as_of_day},"
        f"涨停首次封板时间@{as_of_day},涨停封单额@{as_of_day},"
        f"涨停封单量@{as_of_day},涨停封成比@{as_of_day},"
        f"收盘价@{as_of_day},成交额@{as_of_day},行业"
    )


def historical_large_turnover_strategy_query(as_of_day: str, seed_turnover_yi: int = 30) -> str:
    """Seed broad trend candidates by same-day turnover, then filter by avg10 turnover locally.

    jvQuant semantic query is the universe source here. The user's real rule is
    10-day average turnover above 50 Yi, which is computed from kline data after
    this seed query. The lower same-day seed keeps T-1 shrink candidates in the
    universe even when the as-of day itself traded below 50 Yi.
    """
    safe_seed = max(1, int(seed_turnover_yi or 30))
    return (
        f"成交额@{as_of_day}大于{safe_seed}亿,非ST,"
        f"股票代码,股票简称,涨跌幅@{as_of_day},"
        f"收盘价@{as_of_day},最高价@{as_of_day},成交额@{as_of_day},行业"
    )


def historical_large_turnover_strategy_queries(as_of_day: str, seed_turnover_yi: int = 30) -> list[str]:
    base = historical_large_turnover_strategy_query(as_of_day, seed_turnover_yi)
    safe_seed = max(1, int(seed_turnover_yi or 30))
    growth_board = (
        f"创业板,成交额@{as_of_day}大于{safe_seed}亿,非ST,"
        f"股票代码,股票简称,涨跌幅@{as_of_day},"
        f"收盘价@{as_of_day},最高价@{as_of_day},成交额@{as_of_day},行业"
    )
    return [base, growth_board]


def current_large_turnover_strategy_queries(seed_turnover_yi: int = 30) -> list[str]:
    """Current-session semantic seed when @date queries are unavailable.

    jvQuant may expose current-day semantic fields as names like
    `成交额2026-06-22` even when historical `成交额@YYYY-MM-DD` queries fail.
    These queries are only suitable for current-session preparation/monitoring;
    callers must label them as current-provider facts, not strict historical
    replay facts.
    """
    safe_seed = max(1, int(seed_turnover_yi or 30))
    base = (
        f"成交额大于{safe_seed}亿,非ST,"
        "股票代码,股票简称,涨跌幅,价格,成交额,行业"
    )
    growth_board = (
        f"创业板,成交额大于{safe_seed}亿,非ST,"
        "股票代码,股票简称,涨跌幅,价格,成交额,行业"
    )
    return [base, growth_board]


def historical_limit_up_symbols_query(day: str) -> str:
    return f"是否涨停@{day},股票代码,股票简称"


def historical_limit_up_theme_query(day: str) -> str:
    return f"是否涨停@{day},非ST,股票代码,股票简称,行业,涨跌幅@{day},涨停封单额@{day}"


def payload_fields(payload: Any) -> list[str]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    fields = data.get("fields", []) if isinstance(data, dict) else []
    return [str(item) for item in fields] if isinstance(fields, list) else []


def has_target_day_candidate_facts(fields: list[str], trading_day: str) -> bool:
    dated = [field for field in fields if trading_day in field]
    has_change = any("涨跌幅" in field for field in dated)
    has_turnover = any("成交额" in field for field in dated)
    has_seal = any("封" in field or "涨停" in field for field in dated)
    return has_change and has_turnover and has_seal


def has_as_of_watchlist_facts(fields: list[str], as_of_day: str) -> bool:
    dated = [field for field in fields if as_of_day in field]
    has_change = any("涨跌幅" in field for field in dated)
    has_turnover = any("成交额" in field for field in dated)
    has_seal = any("封" in field or "涨停" in field for field in dated)
    return has_change and has_turnover and has_seal


def has_large_turnover_strategy_facts(fields: list[str], as_of_day: str) -> bool:
    dated = [field for field in fields if as_of_day in field]
    has_change = any("涨跌幅" in field for field in dated)
    has_turnover = any("成交额" in field for field in dated)
    has_price = any("收盘" in field or "最新价" in field for field in dated) or any("收盘" in field for field in fields)
    return has_change and has_turnover and has_price


def limit_up_flag(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "是", "涨停"}:
        return True
    if text in {"0", "false", "no", "n", "否", "未涨停", "不是"}:
        return False
    if "涨停" in text and "未" not in text and "不" not in text:
        return True
    if "否" in text or "未" in text or "不" in text:
        return False
    return None


def kline_rows(client: Any, symbol: str, limit: int = 260) -> list[dict[str, Any]]:
    payload = client.kline(normalize_symbol(symbol), "stock", "前复权", "day", limit)
    return P._kline_rows(payload)


def resolve_adjacent_trading_days(client: Any, trading_day: str, *, require_next: bool = True) -> dict[str, Any]:
    day = trading_day.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return {"ok": False, "error": "trading_day must use YYYY-MM-DD"}

    rows = kline_rows(client, "000001", 320)
    days = sorted({str(row.get("日期") or "").strip() for row in rows if row.get("日期")})
    prev_days = [item for item in days if item < day]
    next_days = [item for item in days if item > day]
    if not prev_days:
        return {"ok": False, "error": f"No previous trading day found before {day}."}
    if require_next and not next_days:
        return {"ok": False, "error": f"No next trading day found after {day}."}
    return {
        "ok": True,
        "trading_day": day,
        "prev_day": prev_days[-1],
        "next_day": next_days[0] if next_days else "",
        "next_day_known": bool(next_days),
        "calendar_source": "jvQuant kline 000001",
    }


def recent_trading_days(client: Any, as_of_day: str, lookback_days: int = 14) -> list[str]:
    safe_limit = max(1, min(int(lookback_days or 14), 30))
    rows = kline_rows(client, "000001", 360)
    days = sorted({str(row.get("日期") or "").strip() for row in rows if row.get("日期")})
    available = [day for day in days if day <= as_of_day]
    return available[-safe_limit:]


def summarize_theme_continuity(
    *,
    theme: str,
    as_of_day: str,
    days: list[str],
    daily_counts: dict[str, int],
    daily_leaders: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    leaders = daily_leaders or {}
    active_days = [day for day in days if daily_counts.get(day, 0) > 0]
    burst_days = [day for day in days if daily_counts.get(day, 0) >= 2]
    last_3 = days[-3:]
    last_3_counts = [daily_counts.get(day, 0) for day in last_3]
    total = sum(daily_counts.get(day, 0) for day in days)
    max_daily = max((daily_counts.get(day, 0) for day in days), default=0)

    label = "weak"
    if len(active_days) >= 5 and len(burst_days) >= 2 and total >= 8:
        label = "persistent"
    elif len(active_days) >= 3 or len(burst_days) >= 1:
        label = "emerging"
    if len(last_3_counts) >= 3 and last_3_counts[-1] < last_3_counts[-2] <= last_3_counts[-3] and max_daily >= 3:
        label = "fading"

    return {
        "data_mode": "historical_provider",
        "theme": theme,
        "as_of_day": as_of_day,
        "lookback_trading_days": len(days),
        "active_days": len(active_days),
        "burst_days": len(burst_days),
        "total_limit_ups": total,
        "max_daily_limit_ups": max_daily,
        "last_3_counts": last_3_counts,
        "daily_counts": [{"trading_day": day, "limit_up_count": daily_counts.get(day, 0)} for day in days],
        "sample_leaders": leaders,
        "continuity_label": label,
        "off_platform_news_checked": False,
        "cls_news_checked": False,
        "notes": [
            "Market-internal continuity only: grouped by jvQuant industry/theme field from historical limit-up pools.",
            "No off-platform news, CLS popup, or semantic sector-news validation is connected yet.",
            "continuity_label is a descriptive fact label, not a buy/sell score.",
        ],
    }


def build_theme_continuity_map(
    client: Any,
    query_fn: Any,
    *,
    themes: list[str],
    as_of_day: str,
    lookback_days: int = 14,
) -> dict[str, dict[str, Any]]:
    target_themes = {theme for theme in themes if theme and theme != "unknown"}
    days = recent_trading_days(client, as_of_day, lookback_days)
    counts_by_theme: dict[str, dict[str, int]] = {theme: {day: 0 for day in days} for theme in target_themes}
    leaders_by_theme: dict[str, dict[str, list[str]]] = {theme: {} for theme in target_themes}
    if not target_themes or not days:
        return {
            theme: summarize_theme_continuity(
                theme=theme,
                as_of_day=as_of_day,
                days=days,
                daily_counts={day: 0 for day in days},
            )
            for theme in target_themes
        }

    for day in days:
        payload = query_fn(historical_limit_up_theme_query(day), sort_key="涨停封单额")
        for row in P._query_rows(payload):
            theme = P._theme_from_row(row)
            if theme not in target_themes:
                continue
            counts_by_theme[theme][day] = counts_by_theme[theme].get(day, 0) + 1
            leaders_by_theme[theme].setdefault(day, [])
            if len(leaders_by_theme[theme][day]) < 3:
                symbol = normalize_symbol(P._symbol_from_row(row))
                name = P._name_from_row(row)
                leaders_by_theme[theme][day].append(f"{symbol} {name}".strip())

    return {
        theme: summarize_theme_continuity(
            theme=theme,
            as_of_day=as_of_day,
            days=days,
            daily_counts=counts_by_theme.get(theme, {}),
            daily_leaders=leaders_by_theme.get(theme, {}),
        )
        for theme in target_themes
    }


def build_historical_candidate(
    row: dict[str, Any],
    *,
    trading_day: str,
    prev_day: str,
    next_day: str,
    query: str,
) -> dict[str, Any]:
    symbol = normalize_symbol(P._symbol_from_row(row))
    turnover_cny = P._parse_cny_amount(P._field_value(row, "成交额"))
    seal_amount_cny = P._parse_cny_amount(P._field_value(row, "涨停封单额", "封单金额", "封单额"))
    seal_to_turnover_ratio = P.float_or_zero(P._field_value(row, "涨停封成比", "封成比"))
    if seal_to_turnover_ratio == 0.0:
        seal_to_turnover_ratio = P._ratio(seal_amount_cny, turnover_cny)

    return {
        "symbol": symbol,
        "name": P._name_from_row(row),
        "trading_day": trading_day,
        "prev_day": prev_day,
        "next_day": next_day,
        "provider": "jvQuant",
        "data_mode": "historical_provider",
        "query": query,
        "change_pct": P.float_or_zero(P._field_value(row, "涨跌幅")),
        "first_limit_up_time": P._time_or_unknown(
            P._field_value(row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
        ),
        "seal_amount_text": str(P._field_value(row, "涨停封单额", "封单金额", "封单额") or ""),
        "seal_amount_cny": seal_amount_cny,
        "seal_volume_text": str(P._field_value(row, "涨停封单量", "封单量") or ""),
        "seal_volume_shares": P._parse_share_amount(P._field_value(row, "涨停封单量", "封单量")),
        "seal_to_turnover_ratio": seal_to_turnover_ratio,
        "close_price": P.float_or_zero(P._field_value(row, "收盘价", "价格", "最新价")),
        "turnover_text": str(P._field_value(row, "成交额") or ""),
        "turnover_cny": turnover_cny,
        "theme": P._theme_from_row(row),
        "source_fields": list(row.keys())[:40],
        "notes": [
            "Facts-only historical second-board candidate row; no program probability or grade.",
            f"Condition: {prev_day} limit-up and {trading_day} gain above 5%, non-ST.",
        ],
    }


def build_historical_first_board_watchlist_item(
    row: dict[str, Any],
    *,
    as_of_day: str,
    prev_day: str,
    target_second_board_day: str,
    query: str,
    previous_day_limit_up: bool | None = None,
) -> dict[str, Any]:
    symbol = normalize_symbol(P._symbol_from_row(row))
    turnover_cny = P._parse_cny_amount(P._field_value(row, "成交额"))
    seal_amount_cny = P._parse_cny_amount(P._field_value(row, "涨停封单额", "封单金额", "封单额"))
    seal_to_turnover_ratio = P.float_or_zero(P._field_value(row, "涨停封成比", "封成比"))
    if seal_to_turnover_ratio == 0.0:
        seal_to_turnover_ratio = P._ratio(seal_amount_cny, turnover_cny)

    first_board_confirmed = previous_day_limit_up is False

    return {
        "symbol": symbol,
        "name": P._name_from_row(row),
        "as_of_day": as_of_day,
        "prev_day": prev_day,
        "target_second_board_day": target_second_board_day,
        "provider": "jvQuant",
        "data_mode": "historical_provider",
        "query": query,
        "previous_day_limit_up": previous_day_limit_up,
        "first_board_confirmed": first_board_confirmed,
        "change_pct": P.float_or_zero(P._field_value(row, "涨跌幅")),
        "first_limit_up_time": P._time_or_unknown(
            P._field_value(row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
        ),
        "seal_amount_text": str(P._field_value(row, "涨停封单额", "封单金额", "封单额") or ""),
        "seal_amount_cny": seal_amount_cny,
        "seal_volume_text": str(P._field_value(row, "涨停封单量", "封单量") or ""),
        "seal_volume_shares": P._parse_share_amount(P._field_value(row, "涨停封单量", "封单量")),
        "seal_to_turnover_ratio": seal_to_turnover_ratio,
        "close_price": P.float_or_zero(P._field_value(row, "收盘价", "价格", "最新价")),
        "turnover_text": str(P._field_value(row, "成交额") or ""),
        "turnover_cny": turnover_cny,
        "theme": P._theme_from_row(row),
        "source_fields": list(row.keys())[:40],
        "notes": [
            "Facts-only as-of first-board watchlist row; no program probability or grade.",
            f"Only uses fields dated {as_of_day} or earlier; target day is {target_second_board_day}.",
        ],
    }


def build_large_turnover_strategy_item(
    row: dict[str, Any],
    *,
    as_of_day: str,
    prev_day: str,
    target_day: str,
    query: str,
) -> dict[str, Any]:
    symbol = normalize_symbol(P._symbol_from_row(row))
    turnover_cny = P._parse_cny_amount(P._field_value(row, "成交额"))
    return {
        "symbol": symbol,
        "name": P._name_from_row(row),
        "as_of_day": as_of_day,
        "prev_day": prev_day,
        "target_second_board_day": target_day,
        "provider": "jvQuant",
        "data_mode": "historical_provider",
        "query": query,
        "change_pct": P.float_or_zero(P._field_value(row, "涨跌幅")),
        "close_price": P.float_or_zero(P._field_value(row, "收盘价", "价格", "最新价")),
        "as_of_high_price": P.float_or_zero(P._field_value(row, "最高价", "最高")),
        "turnover_text": str(P._field_value(row, "成交额") or ""),
        "turnover_cny": turnover_cny,
        "theme": P._theme_from_row(row),
        "source_fields": list(row.keys())[:40],
        "notes": [
            "Facts-only broad trend strategy seed row; no program probability or grade.",
            "Seed condition: as-of-day turnover above provider threshold; 10-day average turnover is verified from kline after enrichment.",
            f"Only uses fields dated {as_of_day} or earlier; target day is {target_day}.",
        ],
    }


def _rows_up_to_day(rows: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("日期") or "") <= day]


def strategy_facts_from_kline(
    client: Any,
    symbol: str,
    *,
    as_of_day: str,
    limit: int = 80,
) -> dict[str, Any]:
    code = normalize_symbol(symbol)
    rows = _rows_up_to_day(kline_rows(client, code, limit), as_of_day)
    if not rows:
        return {
            "symbol": code,
            "strategy_data_mode": "unavailable",
            "strategy_error": "missing_as_of_kline",
            "avg_turnover_10d_cny": 0.0,
            "avg_turnover_10d_pass": False,
            "as_of_turnover_cny": 0.0,
            "prev_day_turnover_cny": 0.0,
            "prev_day_volume_shrink_ratio": 0.0,
            "prev_day_shrink": False,
            "previous_high_price": 0.0,
            "broke_previous_high": False,
            "as_of_high_broke_previous_high": False,
        }

    current = rows[-1]
    history = rows[:-1]
    recent_for_avg = history[-10:] or rows[-10:]
    turn_turnovers = [P.float_or_zero(row.get("成交额")) for row in recent_for_avg]
    avg_10d = avg_turnover_10d(turn_turnovers)
    as_of_turnover = P.float_or_zero(current.get("成交额"))
    shrink_ratio = prev_day_volume_shrink_ratio(prev_day_volume=as_of_turnover, avg_10d=avg_10d)
    prior_highs = [P.float_or_zero(row.get("最高")) for row in history[-20:] if P.float_or_zero(row.get("最高")) > 0]
    previous_high = max(prior_highs, default=0.0)
    current_close = P.float_or_zero(current.get("收盘"))
    current_high = P.float_or_zero(current.get("最高"))

    return {
        "symbol": code,
        "strategy_data_mode": "historical_provider",
        "strategy_error": "",
        "avg_turnover_10d_cny": round(avg_10d, 2),
        "avg_turnover_10d_pass": avg_10d >= 5_000_000_000.0,
        "as_of_turnover_cny": round(as_of_turnover, 2),
        "prev_day_turnover_cny": round(as_of_turnover, 2),
        "prev_day_volume_shrink_ratio": shrink_ratio,
        "prev_day_shrink": 0.0 < shrink_ratio < 1.0,
        "previous_high_price": round(previous_high, 4),
        "broke_previous_high": broke_previous_high(current_price=current_close, prior_highs=prior_highs),
        "as_of_high_broke_previous_high": broke_previous_high(current_price=current_high, prior_highs=prior_highs),
        "current_close": round(current_close, 4),
        "current_high": round(current_high, 4),
        "strategy_notes": [
            "avg_turnover_10d_cny uses the 10 sessions before as_of_day when available.",
            "prev_day_volume_shrink_ratio compares as_of_day turnover (T-1 for the next-session trigger) to that same 10-session turnover baseline.",
            "broke_previous_high uses as_of close versus the prior 20-session high; as_of_high_broke_previous_high uses intraday high.",
            "No program grade or promotion probability is assigned.",
        ],
    }


def outcome_from_kline(
    client: Any,
    symbol: str,
    *,
    trading_day: str,
    next_day: str,
    limit: int = 120,
) -> dict[str, Any]:
    code = normalize_symbol(symbol)
    rows = kline_rows(client, code, limit)
    by_day = {str(row.get("日期") or ""): row for row in rows}
    current = by_day.get(trading_day)
    nxt = by_day.get(next_day)
    if not current or not nxt:
        return {
            "symbol": code,
            "trading_day": trading_day,
            "next_day": next_day,
            "provider": "jvQuant",
            "data_mode": "unavailable",
            "ok": False,
            "error": "missing_day_or_next_day_kline",
        }

    current_close = P.float_or_zero(current.get("收盘"))
    if current_close <= 0:
        return {
            "symbol": code,
            "trading_day": trading_day,
            "next_day": next_day,
            "provider": "jvQuant",
            "data_mode": "unavailable",
            "ok": False,
            "error": "missing_current_close",
        }

    open_pct = (P.float_or_zero(nxt.get("开盘")) - current_close) / current_close * 100.0
    high_pct = (P.float_or_zero(nxt.get("最高")) - current_close) / current_close * 100.0
    low_pct = (P.float_or_zero(nxt.get("最低")) - current_close) / current_close * 100.0
    close_pct = (P.float_or_zero(nxt.get("收盘")) - current_close) / current_close * 100.0
    limit_pct = daily_limit_pct(code)
    touched_limit_up = high_pct >= limit_pct - 0.2
    sealed_next_day = close_pct >= limit_pct - 0.2

    return {
        "symbol": code,
        "trading_day": trading_day,
        "next_day": next_day,
        "provider": "jvQuant",
        "data_mode": "historical_provider",
        "ok": True,
        "current_close": round(current_close, 4),
        "next_day_open_pct": round(open_pct, 2),
        "next_day_high_pct": round(high_pct, 2),
        "next_day_low_pct": round(low_pct, 2),
        "next_day_close_pct": round(close_pct, 2),
        "provider_next_day_change_pct": P.float_or_zero(nxt.get("涨跌幅")),
        "daily_limit_pct": limit_pct,
        "touched_limit_up": touched_limit_up,
        "sealed_next_day": sealed_next_day,
        "broke_after_touch": bool(touched_limit_up and not sealed_next_day),
        "notes": [
            "Outcome derived from jvQuant daily K-line relative to the candidate day's close.",
            "This is objective labeling data for agent calibration, not a program judgment.",
        ],
    }
