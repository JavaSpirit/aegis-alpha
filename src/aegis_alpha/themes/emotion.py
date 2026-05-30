from __future__ import annotations

from aegis_alpha.models import LadderEntry, MarketEmotion


class MarketEmotionGauge:
    def calculate(
        self,
        *,
        trading_day: str,
        yesterday_limitup_today_premium_pct: float = 0.0,
        yesterday_consecutive_boards_alive_count: int = 0,
        yesterday_consecutive_boards_total: int = 0,
        first_board_count: int = 0,
        second_board_count: int = 0,
        third_board_count: int = 0,
        ladder_entries: list[LadderEntry] | None = None,
    ) -> MarketEmotion:
        alive_rate = _ratio(yesterday_consecutive_boards_alive_count, yesterday_consecutive_boards_total)
        first_to_second = _ratio(second_board_count, first_board_count)
        second_to_third = _ratio(third_board_count, second_board_count)
        consecutive_count = max(0, second_board_count + third_board_count)
        max_height = max([entry.consecutive_boards for entry in ladder_entries or []] or [0])
        return MarketEmotion(
            trading_day=trading_day,
            yesterday_limitup_today_premium_pct=yesterday_limitup_today_premium_pct,
            yesterday_consecutive_boards_alive_count=yesterday_consecutive_boards_alive_count,
            yesterday_consecutive_boards_total=yesterday_consecutive_boards_total,
            yesterday_consecutive_boards_alive_rate=alive_rate,
            first_to_second_promotion_rate=first_to_second,
            second_to_third_promotion_rate=second_to_third,
            first_board_to_consecutive_ratio=round(first_board_count / consecutive_count, 4) if consecutive_count else 0.0,
            max_height_today=max_height,
            notes=["Emotion gauge calculated from available ladder and promotion counts."],
        )


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(max(0.0, min(1.0, float(numerator) / float(denominator))), 4)
