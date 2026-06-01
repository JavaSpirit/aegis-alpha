from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from aegis_alpha.clock import SH_TZ
from aegis_alpha.models import (
    CapitalFlowSlice,
    ContrarianPoolEntry,
    DragonTigerRecord,
    DragonTigerSeat,
    MinuteReplayBar,
    NewStockCandidate,
    OrderbookQueueLevel,
    StockOrderbookSnapshot,
    SuspendedStock,
    WeeklyPosition,
)
from aegis_alpha.symbols import normalize_symbol


def float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _query_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    fields = data.get("fields", []) if isinstance(data, dict) else []
    rows = data.get("list", []) if isinstance(data, dict) else []
    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        mapped_rows.append(
            {str(field): row[index] for index, field in enumerate(fields) if index < len(row)}
        )
    return mapped_rows


def _rows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {symbol: row for row in rows if (symbol := _symbol_from_row(row))}


def _query_count(payload: dict[str, Any]) -> int:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    return int_or_zero(data.get("count")) if isinstance(data, dict) else 0


def _latest_minute_day(days: Any) -> dict[str, Any]:
    if not isinstance(days, list):
        return {}
    valid_days = [day for day in days if isinstance(day, dict) and isinstance(day.get("list"), list) and day["list"]]
    if not valid_days:
        return {}
    return sorted(valid_days, key=lambda item: str(item.get("date") or ""))[-1]


def _minute_bars_from_rows(rows: Any, fields: list[Any]) -> list[MinuteReplayBar]:
    if not isinstance(rows, list):
        return []
    time_index = _field_index(fields, "时间", "time")
    price_index = _field_index(fields, "最新价", "价格", "last_price")
    average_index = _field_index(fields, "均价", "average_price", "avg_price")
    volume_index = _field_index(fields, "成交量", "volume")

    bars: list[MinuteReplayBar] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        time_value = _row_value(row, time_index)
        price_value = _row_value(row, price_index)
        if time_value in (None, "") or price_value in (None, ""):
            continue
        bar = MinuteReplayBar(
            time=str(time_value),
            last_price=float_or_zero(price_value),
            average_price=float_or_zero(_row_value(row, average_index)),
            volume=float_or_zero(_row_value(row, volume_index)),
        )
        if bar.last_price > 0:
            bars.append(bar)
    return sorted(bars, key=lambda item: item.time)


def _field_index(fields: list[Any], *prefixes: str) -> int:
    normalized_prefixes = tuple(prefix.lower() for prefix in prefixes)
    for index, field in enumerate(fields):
        field_text = str(field).strip()
        field_lower = field_text.lower()
        if field_text in prefixes or any(field_lower.startswith(prefix) for prefix in normalized_prefixes):
            return index
    return -1


def _row_value(row: list[Any], index: int) -> Any:
    if index < 0 or index >= len(row):
        return None
    return row[index]


def _minute_speed_windows(trading_day: str, bars: list[MinuteReplayBar]) -> tuple[dict[str, float], dict[str, str]]:
    speed_pct_by_window: dict[str, float] = {}
    speed_window_by_window: dict[str, str] = {}
    if len(bars) < 2:
        return speed_pct_by_window, speed_window_by_window

    latest_index = len(bars) - 1
    latest = bars[latest_index]
    for minutes in (1, 3, 5, 10):
        base_index = max(0, latest_index - minutes)
        base = bars[base_index]
        label = f"{minutes}m"
        if base.last_price <= 0:
            speed = 0.0
        else:
            speed = round((latest.last_price / base.last_price - 1.0) * 100.0, 4)
        exactness = "exact" if latest_index - base_index == minutes else "partial"
        speed_pct_by_window[label] = speed
        speed_window_by_window[label] = (
            f"minute_replay_{exactness}_window:"
            f"{trading_day} {_time_with_seconds(base.time)}-"
            f"{trading_day} {_time_with_seconds(latest.time)}"
        )
    return speed_pct_by_window, speed_window_by_window


def _time_with_seconds(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return f"{text}:00"
    return text


def _limitup_from_row(row: dict[str, Any]) -> Any:
    # Imported lazily to avoid circular imports; callers import LimitUpStock directly.
    from aegis_alpha.models import LimitUpStock

    turnover_cny = _parse_cny_amount(_field_value(row, "成交额"))
    seal_amount_cny = _parse_cny_amount(_field_value(row, "涨停封单额", "封单金额", "封单额"))
    seal_to_turnover_ratio = float_or_zero(_field_value(row, "涨停封成比", "封成比"))
    if seal_to_turnover_ratio == 0:
        seal_to_turnover_ratio = _ratio(seal_amount_cny, turnover_cny)
    return LimitUpStock(
        symbol=_symbol_from_row(row),
        name=_name_from_row(row),
        data_mode="live_provider",
        provider="jvQuant",
        theme=_theme_from_row(row),
        first_limit_up_time=_time_or_unknown(
            _field_value(row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
        ),
        seal_amount_cny=seal_amount_cny,
        free_float_market_cap_cny=0.0,
        seal_amount_ratio=seal_to_turnover_ratio,
        reopen_count=0,
        status="sealed",
    )


def _break_board_from_row(row: dict[str, Any]) -> Any:
    from aegis_alpha.models import BreakBoardStock

    return BreakBoardStock(
        symbol=_symbol_from_row(row),
        name=_name_from_row(row),
        data_mode="live_provider",
        provider="jvQuant",
        theme=_theme_from_row(row),
        first_break_time="unknown",
        max_seal_amount_cny=0.0,
        current_change_pct=float_or_zero(_field_value(row, "涨跌幅")),
        reason="jvQuant semantic query matched break-board condition; seal detail is not derived yet.",
    )


def _symbol_from_row(row: dict[str, Any]) -> str:
    return str(_field_value(row, "代码", "股票代码") or "").strip()


def _name_from_row(row: dict[str, Any]) -> str:
    return str(_field_value(row, "名称", "股票简称", "股票名称") or "").strip()


def _theme_from_row(row: dict[str, Any]) -> str:
    return str(_field_value(row, "行业", "行业分类", "所属行业") or "unknown").strip() or "unknown"


def _field_value(row: dict[str, Any], *prefixes: str) -> Any:
    _key, value = _field_entry(row, *prefixes)
    return value


def _field_entry(row: dict[str, Any], *prefixes: str) -> tuple[str, Any]:
    for prefix in prefixes:
        if prefix in row:
            return prefix, row[prefix]
    for key, value in row.items():
        if any(key.startswith(prefix) for prefix in prefixes):
            return key, value
    return "", None


def _first_field_value(rows: list[dict[str, Any]], *prefixes: str) -> Any:
    for row in rows:
        value = _field_value(row, *prefixes)
        if value not in (None, ""):
            return value
    return None


def _parse_cny_amount(value: Any) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0.0
    negative = text.startswith("-")
    text = text.removeprefix("-")
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier = 100_000_000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10_000.0
        text = text[:-1]
    amount = float_or_zero(text) * multiplier
    return -amount if negative else amount


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _latest_date_from_fields(row: dict[str, Any], fallback: str = "") -> str:
    for key in row:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", key)
        if match:
            return match.group(1)
    return fallback


def _kline_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    fields = data.get("fields", []) if isinstance(data, dict) else []
    rows = data.get("list", []) if isinstance(data, dict) else []
    mapped: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, list):
            mapped.append({str(field): row[index] for index, field in enumerate(fields) if index < len(row)})
    return sorted(mapped, key=lambda item: str(item.get("日期") or ""))


def _close_values(rows: list[dict[str, Any]]) -> list[float]:
    return [float_or_zero(row.get("收盘")) for row in rows if float_or_zero(row.get("收盘")) > 0]


def parse_weekly_position_payload(
    week_payload: dict[str, Any],
    day_payload: dict[str, Any],
    *,
    symbol: str,
) -> WeeklyPosition:
    week_rows = _kline_rows(week_payload)
    if not week_rows:
        return WeeklyPosition(
            symbol=normalize_symbol(symbol),
            trading_day="",
            notes=["jvQuant weekly kline returned no rows."],
            provider="jvQuant",
            data_mode="live_provider_empty",
        )

    latest_window = week_rows[-8:]
    latest = latest_window[-1]
    highs = [float_or_zero(row.get("最高")) for row in latest_window]
    lows = [float_or_zero(row.get("最低")) for row in latest_window if float_or_zero(row.get("最低")) > 0]
    weekly_high = max(highs, default=0.0)
    weekly_low = min(lows, default=0.0)
    weekly_close = float_or_zero(latest.get("收盘"))
    denominator = weekly_high - weekly_low
    position_pct = 0.0 if denominator <= 0 else max(0.0, min(1.0, (weekly_close - weekly_low) / denominator))

    closes = _close_values(week_rows)
    weeks_in_uptrend = 0
    for index in range(len(closes) - 1, 0, -1):
        if closes[index] <= closes[index - 1]:
            break
        weeks_in_uptrend += 1

    day_closes = _close_values(_kline_rows(day_payload))
    ma20_above_ma60 = False
    if len(day_closes) >= 60:
        ma20 = sum(day_closes[-20:]) / 20.0
        ma60 = sum(day_closes[-60:]) / 60.0
        ma20_above_ma60 = ma20 > ma60

    return WeeklyPosition(
        symbol=normalize_symbol(symbol),
        trading_day=str(latest.get("日期") or ""),
        weekly_high=weekly_high,
        weekly_low=weekly_low,
        weekly_close=weekly_close,
        position_pct=round(position_pct, 4),
        weeks_in_uptrend=weeks_in_uptrend,
        ma20_above_ma60=ma20_above_ma60,
        notes=[
            "Derived from jvQuant week/day K-line payloads.",
            f"weekly_window_rows={len(latest_window)}",
            f"daily_ma_rows={len(day_closes)}",
        ],
        provider="jvQuant",
        data_mode="live_provider",
    )


def parse_limit_down_pool_payload(
    payload: dict[str, Any],
    *,
    trading_day: str,
) -> list[ContrarianPoolEntry]:
    rows = _query_rows(payload)
    entries: list[ContrarianPoolEntry] = []
    for row in rows:
        symbol = _symbol_from_row(row)
        if not symbol:
            continue
        day = trading_day or _latest_date_from_fields(row)
        entries.append(
            ContrarianPoolEntry(
                symbol=symbol,
                name=_name_from_row(row),
                pool_kind="limit_down",
                trading_day=day,
                consecutive_days=int_or_zero(_field_value(row, "连续跌停天数")),
                change_pct=float_or_zero(_field_value(row, "涨跌幅")),
                notes=[
                    "jvQuant semantic query: limit-down pool.",
                    f"status={_field_value(row, '是否跌停') or ''}",
                    f"turnover_cny={_parse_cny_amount(_field_value(row, '成交额')):.0f}",
                ],
            )
        )
    return entries


def parse_st_pool_payload(
    payload: dict[str, Any],
    *,
    trading_day: str,
) -> list[ContrarianPoolEntry]:
    rows = _query_rows(payload)
    entries: list[ContrarianPoolEntry] = []
    for row in rows:
        symbol = _symbol_from_row(row)
        if not symbol:
            continue
        price = _field_value(row, "收盘价", "价格", "最新价")
        amount = _field_value(row, "成交额")
        entries.append(
            ContrarianPoolEntry(
                symbol=symbol,
                name=_name_from_row(row),
                pool_kind="st",
                trading_day=trading_day or _latest_date_from_fields(row),
                consecutive_days=0,
                change_pct=float_or_zero(_field_value(row, "涨跌幅")),
                notes=[
                    "jvQuant semantic query: ST pool.",
                    f"st_flag={_field_value(row, '是否ST') or ''}",
                    "price_missing=true" if str(price).strip() == "-" else f"price={price}",
                    "turnover_missing=true" if str(amount).strip() == "-" else f"turnover_cny={_parse_cny_amount(amount):.0f}",
                ],
            )
        )
    return entries


def parse_new_stock_candidates_payload(
    payload: dict[str, Any],
    *,
    today: str,
) -> list[NewStockCandidate]:
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    today_date = _parse_date(today)
    rows = _query_rows(payload)
    candidates: list[NewStockCandidate] = []
    for row in rows:
        symbol = _symbol_from_row(row)
        if not symbol:
            continue
        listing_date = str(_field_value(row, "上市日期") or "").strip()
        days = int_or_zero(_field_value(row, "上市天数"))
        if days == 0 and today_date is not None and (listed := _parse_date(listing_date)) is not None:
            days = max(0, (today_date - listed).days)
        free_float = _parse_cny_amount(_field_value(row, "流通市值"))
        candidates.append(
            NewStockCandidate(
                symbol=symbol,
                name=_name_from_row(row),
                listing_date=listing_date,
                days_since_listing=days,
                free_float_market_cap_cny=free_float,
                current_change_pct=float_or_zero(_field_value(row, "涨跌幅")),
                tier=classify_new_stock_tier(days_since_listing=days, free_float_cny=free_float),
                notes=[
                    "jvQuant semantic query: new-stock candidate.",
                    f"industry={_theme_from_row(row)}",
                ],
                provider="jvQuant",
                data_mode="live_provider",
            )
        )
    return candidates


def parse_suspended_stocks_payload(
    payload: dict[str, Any],
    *,
    trading_day: str,
) -> list[SuspendedStock]:
    rows = _query_rows(payload)
    suspended: list[SuspendedStock] = []
    for row in rows:
        symbol = _symbol_from_row(row)
        if not symbol:
            continue
        start_day = str(_field_value(row, "停牌起始日期", "停牌起始日") or trading_day).strip()
        end_day = str(_field_value(row, "复牌日", "复牌") or "").strip()
        suspended.append(
            SuspendedStock(
                symbol=symbol,
                name=_name_from_row(row),
                suspension_start_day=start_day if start_day != "-" else trading_day,
                suspension_end_day="" if end_day == "-" else end_day,
                reason=str(_field_value(row, "停牌原因") or "").strip(),
                notes=[
                    "jvQuant semantic query: suspended stock fields confirmed.",
                    f"raw_status={_field_value(row, '停牌') or ''}",
                ],
                provider="jvQuant",
                data_mode="live_provider",
            )
        )
    return suspended


def _dragon_tiger_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return items
    for block in value:
        if not isinstance(block, dict):
            continue
        for item in block.get("list") or []:
            if isinstance(item, dict):
                merged = dict(item)
                merged.setdefault("date", block.get("date"))
                merged.setdefault("filter", block.get("filter"))
                items.append(merged)
    return items


def parse_jvquant_dragon_tiger_payload(
    payload: dict[str, Any],
    *,
    symbol: str,
    trading_day: str,
) -> DragonTigerRecord:
    target = normalize_symbol(symbol)
    rows = _query_rows(payload)
    matched = [row for row in rows if normalize_symbol(_symbol_from_row(row)) == target]
    row = matched[0] if matched else {}
    if not row:
        return DragonTigerRecord(
            symbol=target,
            name="",
            trading_day=trading_day,
            list_reason="not present in jvQuant dragon-tiger semantic-query result",
            provider="jvQuant",
            data_mode="live_provider_empty",
            created_at=datetime.now(SH_TZ).isoformat(timespec="seconds"),
        )

    _key, tiger_value = _field_entry(row, "龙虎榜")
    items = _dragon_tiger_items(tiger_value)
    seats: list[DragonTigerSeat] = []
    total_buy = 0.0
    total_sell = 0.0
    reasons: list[str] = []
    for item in items:
        buy = _parse_cny_amount(item.get("买入额(元)") or item.get("买入金额"))
        sell = _parse_cny_amount(item.get("卖出额(元)") or item.get("卖出金额"))
        net = _parse_cny_amount(item.get("净买额(元)") or item.get("净买入额"))
        if net == 0.0 and (buy or sell):
            net = buy - sell
        total_buy += buy
        total_sell += sell
        reason = str(item.get("上榜原因") or item.get("filter") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
        seat_label = str(item.get("龙虎榜榜单类型") or item.get("上榜原因解读") or "龙虎榜汇总").strip()
        seats.append(
            DragonTigerSeat(
                seat_name=seat_label,
                seat_type="unknown",
                buy_amount_cny=buy,
                sell_amount_cny=sell,
                net_amount_cny=net,
            )
        )

    return DragonTigerRecord(
        symbol=target,
        name=_name_from_row(row),
        trading_day=trading_day or _latest_date_from_fields(row),
        list_reason="; ".join(reasons[:3]),
        total_buy_cny=total_buy,
        total_sell_cny=total_sell,
        net_amount_cny=total_buy - total_sell,
        seats=seats,
        provider="jvQuant",
        data_mode="live_provider",
        created_at=datetime.now(SH_TZ).isoformat(timespec="seconds"),
    )


def parse_daily_capital_flow_payload(
    payload: dict[str, Any],
    *,
    symbol: str,
    trading_day: str,
) -> list[CapitalFlowSlice]:
    rows = _query_rows(payload)
    target = normalize_symbol(symbol)
    row = next((item for item in rows if normalize_symbol(_symbol_from_row(item)) == target), None)
    if row is None:
        return []
    main = _parse_cny_amount(_field_value(row, "主力净额"))
    super_big = _parse_cny_amount(_field_value(row, "超大单净额"))
    big = _parse_cny_amount(_field_value(row, "大单净额"))
    mid = _parse_cny_amount(_field_value(row, "中单净额"))
    small = _parse_cny_amount(_field_value(row, "小单净额"))
    day = trading_day or _latest_date_from_fields(row)
    return [
        CapitalFlowSlice(
            symbol=target,
            trading_day=day,
            window="daily",
            big_order_net_inflow_cny=super_big + big if (super_big or big) else main,
            main_capital_net_inflow_cny=main,
            retail_capital_net_inflow_cny=mid + small,
            notes=[
                "jvQuant semantic daily capital-flow fields.",
                "Not minute-level Level2 order classification.",
                f"super_big_net_cny={super_big:.0f}",
                f"big_net_cny={big:.0f}",
                f"mid_net_cny={mid:.0f}",
                f"small_net_cny={small:.0f}",
            ],
            provider="jvQuant",
            data_mode="live_provider",
            created_at=datetime.now(SH_TZ).isoformat(timespec="seconds"),
        )
    ]


def _parse_share_amount(value: Any) -> float:
    text = str(value or "").strip().replace(",", "")
    text = text.replace("股", "")
    return _parse_cny_amount(text)


def _time_or_unknown(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"0", "None", "nan", "NaN"}:
        return "unknown"
    return _normalize_time_string(text)


def _normalize_time_string(text: str) -> str:
    match = re.fullmatch(
        r"(?:\d{4}-\d{2}-\d{2}[ T])?(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[+-]\d{2}:\d{2})?",
        text,
    )
    if not match:
        return "unknown"
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
        return "unknown"
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _speed_window_from_field(field_name: str, query_timestamp: str) -> tuple[str, str, bool]:
    match = re.search(
        r"@(?P<start>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})-(?P<end>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
        field_name,
    )
    if not match:
        return "provider_latest_rolling_5m", query_timestamp, False

    start = match.group("start")
    end = match.group("end")
    timestamp = _iso_from_provider_datetime(end) or query_timestamp
    return f"provider_exact_window:{start}-{end}", timestamp, True


def _speed_from_row(row: dict[str, Any], query_timestamp: str) -> tuple[float, str, str, bool]:
    field, value = _field_entry(row, "涨速", "区间涨跌幅")
    window, timestamp, has_exact_window = _speed_window_from_field(field, query_timestamp)
    return float_or_zero(value), window, timestamp, has_exact_window


def _iso_from_provider_datetime(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH_TZ)
    except ValueError:
        return ""
    return parsed.isoformat(timespec="seconds")


def _queue_position_note(orderbook: StockOrderbookSnapshot) -> str:
    if not orderbook.bid_levels and not orderbook.ask_levels:
        return "Orderbook queue unavailable from provider; own-order queue position cannot be inferred."
    best_bid = orderbook.bid_levels[0] if orderbook.bid_levels else None
    best_ask = orderbook.ask_levels[0] if orderbook.ask_levels else None
    parts = ["Own-order queue position unavailable until Aegis Alpha tracks a submitted order."]
    if best_bid is not None:
        parts.append(
            f"best_bid_queue price={best_bid.price}, volume={best_bid.volume_count:.0f}, queue_count={best_bid.queue_count}."
        )
    if best_ask is not None:
        parts.append(
            f"best_ask_queue price={best_ask.price}, volume={best_ask.volume_count:.0f}, queue_count={best_ask.queue_count}."
        )
    return " ".join(parts)


def _parse_level(row: dict[str, Any]) -> OrderbookQueueLevel:
    label = str(row.get("type") or "")
    side = "unknown"
    if label.startswith("B"):
        side = "bid"
    elif label.startswith("S"):
        side = "ask"

    return OrderbookQueueLevel(
        side=side,
        level_label=label,
        price=float_or_zero(row.get("price")),
        volume_count=float_or_zero(row.get("volume_count")),
        queue_count=int_or_zero(row.get("queue_count")),
        queue_slice=str(row.get("queue_slice") or ""),
    )


def _tags_from_row(row: dict[str, Any], *prefixes: str) -> list[str]:
    values: list[str] = []
    for prefix in prefixes:
        value = _field_value(row, prefix)
        if value is None:
            continue
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value)
        else:
            text = str(value).strip()
            bracket_tags = re.findall(r"【([^】]+)】", text)
            if bracket_tags:
                values.extend(part.strip() for part in bracket_tags)
            else:
                text = re.sub(r"[\[\]\"'【】]", "", text)
                values.extend(part.strip() for part in re.split(r"[,，;；、|/]+", text))
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        tags.append(value)
    return tags[:20]


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(max(-1.0, min(1.0, numerator / denominator)), 4)


def _leading_themes(stocks: list[Any]) -> list[str]:
    from collections import Counter

    counter = Counter(stock.theme for stock in stocks if stock.theme and stock.theme != "unknown")
    return [theme for theme, _count in counter.most_common(5)]
