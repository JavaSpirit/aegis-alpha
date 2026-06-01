from __future__ import annotations

from aegis_alpha.models import SuspendedStock


def is_symbol_suspended(
    symbol: str,
    *,
    trading_day: str,
    suspended: list[SuspendedStock],
) -> bool:
    for s in suspended:
        if s.symbol != symbol:
            continue
        if s.suspension_start_day > trading_day:
            continue
        if s.suspension_end_day and s.suspension_end_day < trading_day:
            continue
        return True
    return False
