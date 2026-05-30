from __future__ import annotations

from aegis_alpha.models import LadderEntry
from aegis_alpha.themes.emotion import MarketEmotionGauge


def test_market_emotion_gauge_calculates_rates() -> None:
    emotion = MarketEmotionGauge().calculate(
        trading_day="2026-05-29",
        yesterday_consecutive_boards_alive_count=3,
        yesterday_consecutive_boards_total=4,
        first_board_count=20,
        second_board_count=5,
        third_board_count=2,
        ladder_entries=[
            LadderEntry(symbol="600000", trading_day="2026-05-29", consecutive_boards=4, height_label="fourth_board")
        ],
    )

    assert emotion.yesterday_consecutive_boards_alive_rate == 0.75
    assert emotion.first_to_second_promotion_rate == 0.25
    assert emotion.max_height_today == 4
