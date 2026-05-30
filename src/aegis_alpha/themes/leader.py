from __future__ import annotations

from collections import defaultdict

from aegis_alpha.models import LadderEntry, LimitUpStock, ThemeLeader


class ThemeLeaderResolver:
    def resolve(
        self,
        stocks: list[LimitUpStock],
        ladder_entries: dict[str, LadderEntry],
        *,
        trading_day: str,
    ) -> list[ThemeLeader]:
        by_theme: dict[str, list[LimitUpStock]] = defaultdict(list)
        for stock in stocks:
            if stock.theme and stock.theme != "unknown":
                by_theme[stock.theme].append(stock)

        leaders: list[ThemeLeader] = []
        for theme, members in by_theme.items():
            ranked = sorted(
                members,
                key=lambda item: (
                    ladder_entries.get(item.symbol, LadderEntry(symbol=item.symbol, trading_day=trading_day, consecutive_boards=1)).consecutive_boards,
                    item.seal_amount_cny,
                    _time_rank(item.first_limit_up_time),
                ),
                reverse=True,
            )
            leader = ranked[0]
            leader_ladder = ladder_entries.get(
                leader.symbol,
                LadderEntry(symbol=leader.symbol, trading_day=trading_day, consecutive_boards=1, height_label="first_board"),
            )
            leaders.append(
                ThemeLeader(
                    theme=theme,
                    trading_day=trading_day,
                    leader_symbol=leader.symbol,
                    leader_name=leader.name,
                    leader_consecutive_boards=leader_ladder.consecutive_boards,
                    leader_first_limit_up_time=leader.first_limit_up_time,
                    leader_seal_amount_cny=leader.seal_amount_cny,
                    leader_status=leader.status,
                    co_leader_symbols=[item.symbol for item in ranked[1:3]],
                    member_count=len(members),
                    notes=["Leader ranked by ladder height, seal amount, and first seal time."],
                )
            )
        return sorted(leaders, key=lambda item: (item.member_count, item.leader_consecutive_boards), reverse=True)


def _time_rank(value: str) -> int:
    if not value or value == "unknown":
        return 0
    try:
        hour, minute, second = [int(part) for part in value.split(":")]
    except ValueError:
        return 0
    return 24 * 3600 - (hour * 3600 + minute * 60 + second)
