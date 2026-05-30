from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aegis_alpha.clock import SH_TZ, now_dt, now_iso, parse_iso


def test_now_iso_returns_iso8601_with_offset() -> None:
    text = now_iso()
    parsed = datetime.fromisoformat(text)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == ZoneInfo("Asia/Shanghai").utcoffset(parsed)


def test_now_dt_is_timezone_aware() -> None:
    dt = now_dt()

    assert dt.tzinfo is not None
    assert dt.utcoffset() == ZoneInfo("Asia/Shanghai").utcoffset(dt)


def test_parse_iso_attaches_sh_tz_when_naive() -> None:
    parsed = parse_iso("2026-05-29T10:00:00")

    assert parsed is not None
    assert parsed.tzinfo == SH_TZ


def test_parse_iso_returns_none_for_invalid_or_empty_values() -> None:
    assert parse_iso("not-a-time") is None
    assert parse_iso("") is None
    assert parse_iso("   ") is None


def test_parse_iso_keeps_explicit_offset() -> None:
    parsed = parse_iso("2026-05-29T10:00:00+09:00")

    assert parsed is not None
    assert parsed.utcoffset() == ZoneInfo("Asia/Tokyo").utcoffset(parsed)
