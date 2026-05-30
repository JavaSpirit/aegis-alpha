from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


SH_TZ = ZoneInfo("Asia/Shanghai")


def now_dt() -> datetime:
    return datetime.now(SH_TZ)


def now_iso() -> str:
    return now_dt().isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=SH_TZ)
    return parsed
