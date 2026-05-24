from __future__ import annotations

import json

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def main() -> None:
    adapter = MockMarketDataAdapter()
    payloads = {
        "market_snapshot": adapter.get_market_snapshot().model_dump(),
        "limitup_pool": [item.model_dump() for item in adapter.get_limitup_pool()],
        "break_board_pool": [item.model_dump() for item in adapter.get_break_board_pool()],
        "stock_realtime_snapshot": adapter.get_stock_realtime_snapshot("600000.SH").model_dump(),
        "stock_history_limitup_stats": adapter.get_stock_history_limitup_stats("600000.SH").model_dump(),
        "theme_strength": adapter.get_theme_strength("600000.SH").model_dump(),
        "candidate_explanation": adapter.explain_candidate("600000.SH").model_dump(),
    }

    print(json.dumps(payloads, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

