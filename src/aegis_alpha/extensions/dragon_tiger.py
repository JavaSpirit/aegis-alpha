from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    DragonTigerRecord,
    DragonTigerSeat,
    DragonTigerSeatType,
)


@dataclass(frozen=True)
class HotMoneyEntry:
    alias: str
    seat_match: tuple[str, ...]


@dataclass(frozen=True)
class SeatWhitelist:
    hot_money: tuple[HotMoneyEntry, ...]
    institution_keywords: tuple[str, ...]
    hk_connect_keywords: tuple[str, ...]


def load_seat_whitelist(config_path: str) -> SeatWhitelist:
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    hot_money_raw = raw.get("hot_money_known") or []
    hot_money = tuple(
        HotMoneyEntry(
            alias=str(item.get("alias", "")).strip(),
            seat_match=tuple(str(s).strip() for s in (item.get("seat_match") or [])),
        )
        for item in hot_money_raw
        if item.get("alias")
    )
    institution_keywords = tuple(
        str(k).strip() for k in (raw.get("institution_keywords") or []) if str(k).strip()
    )
    hk_connect_keywords = tuple(
        str(k).strip() for k in (raw.get("hk_connect_keywords") or []) if str(k).strip()
    )
    return SeatWhitelist(
        hot_money=hot_money,
        institution_keywords=institution_keywords,
        hk_connect_keywords=hk_connect_keywords,
    )


def classify_seat(
    seat_name: str, whitelist: SeatWhitelist
) -> tuple[DragonTigerSeatType, str]:
    name = (seat_name or "").strip()
    if not name:
        return "unknown", ""
    for entry in whitelist.hot_money:
        for match in entry.seat_match:
            if match and match in name:
                return "hot_money_known", entry.alias
    for keyword in whitelist.institution_keywords:
        if keyword and keyword in name:
            return "institution", ""
    for keyword in whitelist.hk_connect_keywords:
        if keyword and keyword in name:
            return "hk_connect", ""
    return "hot_money_unknown", ""


def _safe_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_dragon_tiger_payload(
    raw: dict[str, Any],
    *,
    whitelist: SeatWhitelist,
    provider: str = "mock",
    data_mode: str = "mock",
) -> DragonTigerRecord:
    symbol = str(raw.get("symbol", "")).strip()
    name = str(raw.get("name", "")).strip()
    trading_day = str(raw.get("trading_day", "")).strip()
    list_reason = str(raw.get("list_reason", "")).strip()

    buy_rows = raw.get("buy_seats") or []
    sell_rows = raw.get("sell_seats") or []

    seats: list[DragonTigerSeat] = []
    total_buy = 0.0
    total_sell = 0.0
    for row in buy_rows:
        amount = _safe_float(row.get("amount"))
        seat_type, alias = classify_seat(str(row.get("seat_name", "")), whitelist)
        seats.append(
            DragonTigerSeat(
                seat_name=str(row.get("seat_name", "")),
                seat_type=seat_type,
                hot_money_alias=alias,
                buy_amount_cny=amount,
                sell_amount_cny=0.0,
                net_amount_cny=amount,
            )
        )
        total_buy += amount
    for row in sell_rows:
        amount = _safe_float(row.get("amount"))
        seat_type, alias = classify_seat(str(row.get("seat_name", "")), whitelist)
        seats.append(
            DragonTigerSeat(
                seat_name=str(row.get("seat_name", "")),
                seat_type=seat_type,
                hot_money_alias=alias,
                buy_amount_cny=0.0,
                sell_amount_cny=amount,
                net_amount_cny=-amount,
            )
        )
        total_sell += amount

    return DragonTigerRecord(
        symbol=symbol,
        name=name,
        trading_day=trading_day,
        list_reason=list_reason,
        total_buy_cny=total_buy,
        total_sell_cny=total_sell,
        net_amount_cny=total_buy - total_sell,
        seats=seats,
        provider=provider,
        data_mode=data_mode,
        created_at=now_iso(),
    )
