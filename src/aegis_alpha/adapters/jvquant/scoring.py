from __future__ import annotations

from typing import Any

from aegis_alpha.grading import CandidateGradingConfig


def market_score(
    limit_up_count: int,
    break_board_rate: float,
    hot_theme_count: int,
    config: CandidateGradingConfig,
) -> float:
    market = config.market
    score = market.base_score
    score += min(market.limit_up_cap, limit_up_count * market.limit_up_weight)
    score += min(market.hot_theme_cap, hot_theme_count * market.hot_theme_weight)
    score -= break_board_rate * market.break_board_penalty
    return round(max(0.0, min(100.0, score)), 2)


def sentiment_from_score(score: float, config: CandidateGradingConfig) -> str:
    market = config.market
    if score >= market.sentiment_hot:
        return "hot"
    if score >= market.sentiment_warm:
        return "warm"
    if score >= market.sentiment_mixed:
        return "mixed"
    return "cold"


def action_from_score(score: float, break_board_rate: float, config: CandidateGradingConfig) -> str:
    market = config.market
    if break_board_rate >= market.avoid_break_board_rate or score < market.avoid_score_below:
        return "avoid"
    if break_board_rate >= market.defensive_break_board_rate or score < market.defensive_score_below:
        return "defensive"
    if score >= market.active_score_at_least and break_board_rate < market.active_break_board_below:
        return "active"
    return "selective"


def seal_quality_score(
    *,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> float:
    seal_cfg = config.seal_quality
    score = 0.0
    if first_limit_up_time != "unknown":
        if first_limit_up_time <= seal_cfg.early_time:
            score += seal_cfg.early_score
        elif first_limit_up_time <= seal_cfg.morning_time:
            score += seal_cfg.morning_score
        elif first_limit_up_time <= seal_cfg.afternoon_time:
            score += seal_cfg.afternoon_score
    if seal_amount_cny >= seal_cfg.large_seal_amount_cny:
        score += seal_cfg.large_seal_score
    elif seal_amount_cny >= seal_cfg.medium_seal_amount_cny:
        score += seal_cfg.medium_seal_score
    elif seal_amount_cny >= seal_cfg.small_seal_amount_cny:
        score += seal_cfg.small_seal_score
    if seal_to_turnover_ratio >= seal_cfg.strong_seal_to_turnover_ratio:
        score += seal_cfg.strong_ratio_score
    elif seal_to_turnover_ratio >= seal_cfg.medium_seal_to_turnover_ratio:
        score += seal_cfg.medium_ratio_score
    elif seal_to_turnover_ratio >= seal_cfg.small_seal_to_turnover_ratio:
        score += seal_cfg.small_ratio_score
    return round(min(100.0, score), 2)


def candidate_grade(
    *,
    action: str,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> str:
    if action == "avoid":
        return "REJECT"
    candidate_cfg = config.candidate
    if change_pct < candidate_cfg.reject_change_pct_below:
        return "REJECT"
    seal_q = seal_quality_score(
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        config=config,
    )
    if action == "defensive":
        return (
            "B"
            if change_pct >= candidate_cfg.strong_change_pct
            and theme_count >= candidate_cfg.a_theme_count
            and (
                orderbook_quality >= candidate_cfg.defensive_orderbook_quality
                or big_order_net_inflow_ratio >= candidate_cfg.defensive_big_order_ratio
                or seal_q >= candidate_cfg.defensive_seal_quality
            )
            else "C"
        )
    if (
        change_pct >= candidate_cfg.strong_change_pct
        and five_min_speed_pct >= candidate_cfg.a_five_min_speed_pct
        and big_order_net_inflow_ratio >= candidate_cfg.a_big_order_ratio
        and orderbook_quality >= candidate_cfg.a_orderbook_quality
        and theme_count >= candidate_cfg.a_theme_count
        and seal_q >= candidate_cfg.a_seal_quality
    ):
        return "A"
    if change_pct >= candidate_cfg.b_change_pct and (
        orderbook_quality >= candidate_cfg.b_orderbook_quality
        or big_order_net_inflow_ratio > 0
        or seal_q >= candidate_cfg.b_seal_quality
    ):
        return "B"
    return "C"


def candidate_grade_reason(
    *,
    action: str,
    grade: str,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    queue_position_note: str,
    limitup_driver_type: str = "unknown",
    intraday_pattern: str = "unknown",
) -> str:
    seal_text = (
        f"首次封板时间为 {first_limit_up_time}，封单额约 {seal_amount_cny / 100_000_000:.2f} 亿元，"
        f"封成比为 {seal_to_turnover_ratio:.2f}"
    )
    if grade == "REJECT":
        reason = (
            "评级为 REJECT，因为当前市场闸门或个股强度不满足二板候选的最低观察条件，"
            "不应按打板候选处理。"
        )
    elif grade == "C":
        if action == "defensive":
            reason = (
                f"评级为 C，主要因为市场闸门为 defensive，说明炸板率或市场风险偏高；"
                f"虽然个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量评分为 {orderbook_quality:.1f}，"
                f"同题材候选数为 {theme_count}；{seal_text}。{queue_position_note}"
            )
        else:
            reason = (
                f"评级为 C，因为个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量、题材联动或数据完整性不足，"
                f"暂时只能作为观察对象；{seal_text}。"
            )
    elif grade == "B":
        reason = (
            f"评级为 B，因为个股当前涨幅达到 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
            f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，同题材候选数为 {theme_count}，具备观察价值；"
            f"盘口质量评分为 {orderbook_quality:.1f}，{seal_text}；但真实委托排队位置和历史溢价数据仍未接入，"
            "不能提高到 A。"
        )
    else:
        reason = (
            f"评级为 A，因为市场闸门允许进攻，个股涨幅为 {change_pct:.2f}%，五分钟涨速为 "
            f"{five_min_speed_pct:.2f}%，资金净流入占比为 {big_order_net_inflow_ratio:.2%}，"
            f"盘口质量评分为 {orderbook_quality:.1f}，同题材候选数为 {theme_count}，且{seal_text}；"
            "仍需在实盘时继续核验数据时效和封单稳定性。"
        )
    if limitup_driver_type != "unknown":
        reason += f" (driver={limitup_driver_type})"
    if intraday_pattern not in {"unknown", "normal"}:
        reason += f" (pattern={intraday_pattern})"
    return reason


def estimated_seal_probability(
    *,
    action: str,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> float:
    probability = 0.25
    probability += min(0.30, max(0.0, change_pct - 5.0) * 0.05)
    probability += min(0.10, max(0.0, five_min_speed_pct) * 0.025)
    probability += min(0.15, max(0.0, big_order_net_inflow_ratio) * 1.5)
    probability += min(0.20, max(0.0, orderbook_quality - 50.0) / 100.0)
    probability += min(0.15, theme_count * 0.03)
    probability += min(
        0.12,
        seal_quality_score(
            first_limit_up_time=first_limit_up_time,
            seal_amount_cny=seal_amount_cny,
            seal_to_turnover_ratio=seal_to_turnover_ratio,
            config=config,
        ) / 1000.0,
    )
    if action == "active":
        probability += 0.10
    elif action == "defensive":
        probability -= 0.12
    elif action == "avoid":
        probability -= 0.25
    return round(max(0.0, min(0.95, probability)), 4)


def theme_position_label(*, theme_max_height: int, theme_multi_board_count: int) -> str:
    if theme_max_height >= 4 or (theme_max_height >= 3 and theme_multi_board_count >= 3):
        return "extended"
    if theme_max_height == 3 or theme_multi_board_count >= 3:
        return "maturing"
    if theme_max_height == 2:
        return "early"
    return "unknown"


def third_board_promotion_assessment(
    *,
    action: str,
    theme_role: str,
    theme_position: str,
    theme_max_height: int,
    theme_multi_board_count: int,
    theme_recent_active_days: int,
    theme_recent_max_member_count: int,
    free_float_market_cap_cny: float,
    turnover_cny: float,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    first_limit_up_time: str,
    break_board_count: int,
    reseal_count: int,
    final_seal_time: str,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    auction_change_pct: float,
    auction_turnover_cny: float,
    weekly_health_score: float,
    config: CandidateGradingConfig,
) -> dict[str, Any]:
    score = 50.0
    reasons: list[str] = []

    action_delta = {"active": 8.0, "selective": 3.0, "defensive": -8.0, "avoid": -22.0}.get(action, 0.0)
    score += action_delta
    reasons.append(f"市场闸门={action}({action_delta:+.0f})")

    theme_delta = {"early": 8.0, "maturing": -5.0, "extended": -14.0}.get(theme_position, -2.0)
    score += theme_delta
    reasons.append(
        f"题材阶段={theme_position}, 最高板={theme_max_height}, 多板数={theme_multi_board_count}, "
        f"近活跃={theme_recent_active_days}天, 最大成员={theme_recent_max_member_count}({theme_delta:+.0f})"
    )

    role_delta = {"leader": 5.0, "co_leader": 3.0, "follower": -3.0}.get(theme_role, 0.0)
    score += role_delta
    if role_delta:
        reasons.append(f"题材角色={theme_role}({role_delta:+.0f})")

    if free_float_market_cap_cny <= 0:
        float_delta = -2.0
        float_label = "unknown"
    elif free_float_market_cap_cny <= 3_000_000_000:
        float_delta = 6.0
        float_label = "small"
    elif free_float_market_cap_cny <= 8_000_000_000:
        float_delta = 3.0
        float_label = "mid"
    elif free_float_market_cap_cny <= 20_000_000_000:
        float_delta = -2.0
        float_label = "large"
    else:
        float_delta = -8.0
        float_label = "mega"
    score += float_delta
    reasons.append(f"流通市值={float_label}({float_delta:+.0f})")

    if turnover_cny <= 0:
        turnover_delta = -2.0
        turnover_label = "unknown"
    elif turnover_cny < 200_000_000:
        turnover_delta = -6.0
        turnover_label = "thin"
    elif turnover_cny <= 1_500_000_000:
        turnover_delta = 5.0
        turnover_label = "healthy"
    elif turnover_cny <= 3_500_000_000:
        turnover_delta = 1.0
        turnover_label = "heavy"
    else:
        turnover_delta = -6.0
        turnover_label = "too_heavy"
    score += turnover_delta
    reasons.append(f"成交额={turnover_label}({turnover_delta:+.0f})")

    seal_q = seal_quality_score(
        first_limit_up_time=first_limit_up_time,
        seal_amount_cny=seal_amount_cny,
        seal_to_turnover_ratio=seal_to_turnover_ratio,
        config=config,
    )
    seal_delta = min(15.0, seal_q * 0.22)
    score += seal_delta
    reasons.append(f"封板质量={seal_q:.0f}({seal_delta:+.0f})")

    if break_board_count == 0:
        reseal_delta = 8.0
        reseal_label = "未炸板"
    elif break_board_count == 1 and reseal_count >= 1:
        reseal_delta = 2.0
        reseal_label = "一次炸板回封"
    elif break_board_count == 2 and reseal_count >= 2:
        reseal_delta = -5.0
        reseal_label = "多次炸板回封"
    else:
        reseal_delta = -12.0
        reseal_label = "回封弱"
    if final_seal_time != "unknown":
        if final_seal_time <= "10:00:00":
            reseal_delta += 3.0
        elif final_seal_time >= "14:30:00":
            reseal_delta -= 6.0
    score += reseal_delta
    reasons.append(f"回封力度={reseal_label}({reseal_delta:+.0f})")

    capital_delta = 0.0
    if big_order_net_inflow_ratio >= 0.05:
        capital_delta = 7.0
    elif big_order_net_inflow_ratio >= 0.02:
        capital_delta = 3.0
    elif big_order_net_inflow_ratio < 0:
        capital_delta = -7.0
    score += capital_delta
    reasons.append(f"资金净流入占比={big_order_net_inflow_ratio:.2%}({capital_delta:+.0f})")

    if orderbook_quality >= 65:
        score += 4.0
        reasons.append("盘口质量偏强(+4)")
    elif orderbook_quality < 45:
        score -= 4.0
        reasons.append("盘口质量偏弱(-4)")

    if auction_change_pct >= 2.0 and auction_turnover_cny >= 30_000_000:
        score += 3.0
        reasons.append("竞价承接较强(+3)")
    elif auction_change_pct < 0:
        score -= 3.0
        reasons.append("竞价偏弱(-3)")

    if weekly_health_score >= 70:
        score += 4.0
        reasons.append("周线位置健康(+4)")
    elif weekly_health_score <= 35:
        score -= 4.0
        reasons.append("周线位置偏弱(-4)")

    score = round(max(0.0, min(100.0, score)), 2)
    probability_pct = round(max(5.0, min(90.0, score * 0.86)), 2)
    if score >= 75:
        promotion_grade = "A"
    elif score >= 62:
        promotion_grade = "B"
    elif score >= 48:
        promotion_grade = "C"
    else:
        promotion_grade = "D"

    return {
        "promotion_score": score,
        "third_board_probability_pct": probability_pct,
        "promotion_grade": promotion_grade,
        "promotion_reason": "；".join(reasons[:8]),
    }
