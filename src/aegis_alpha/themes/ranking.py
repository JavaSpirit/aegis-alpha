from __future__ import annotations

from aegis_alpha.models import ThemeLeader, ThemeRanking, ThemeRotationEntry


def compute_top_themes(
    leaders: list[ThemeLeader],
    *,
    trading_day: str,
    limit: int = 10,
) -> list[ThemeRanking]:
    valid = [leader for leader in leaders if leader.member_count > 0]
    valid.sort(
        key=lambda leader: (
            leader.member_count,
            leader.leader_consecutive_boards,
            leader.leader_seal_amount_cny,
        ),
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 10), 50))
    rankings: list[ThemeRanking] = []
    for index, leader in enumerate(valid[:safe_limit]):
        score = min(
            100.0,
            leader.member_count * 10.0
            + leader.leader_consecutive_boards * 8.0,
        )
        rankings.append(
            ThemeRanking(
                theme=leader.theme,
                trading_day=trading_day,
                rank=index + 1,
                member_count=leader.member_count,
                leader_symbol=leader.leader_symbol,
                leader_consecutive_boards=leader.leader_consecutive_boards,
                score=round(score, 2),
            )
        )
    return rankings


def theme_rotation_diff(
    *,
    today_themes: list[str],
    yesterday_themes: list[str],
    trading_day: str,
) -> ThemeRotationEntry:
    today_set = set(today_themes)
    yesterday_set = set(yesterday_themes)
    return ThemeRotationEntry(
        trading_day=trading_day,
        top_themes=today_themes,
        new_themes=sorted(today_set - yesterday_set),
        fading_themes=sorted(yesterday_set - today_set),
    )
