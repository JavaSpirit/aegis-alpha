from __future__ import annotations

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
) -> str:
    seal_text = (
        f"首次封板时间为 {first_limit_up_time}，封单额约 {seal_amount_cny / 100_000_000:.2f} 亿元，"
        f"封成比为 {seal_to_turnover_ratio:.2f}"
    )
    if grade == "REJECT":
        return (
            "评级为 REJECT，因为当前市场闸门或个股强度不满足二板候选的最低观察条件，"
            "不应按打板候选处理。"
        )
    if grade == "C":
        if action == "defensive":
            return (
                f"评级为 C，主要因为市场闸门为 defensive，说明炸板率或市场风险偏高；"
                f"虽然个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量评分为 {orderbook_quality:.1f}，"
                f"同题材候选数为 {theme_count}；{seal_text}。{queue_position_note}"
            )
        return (
            f"评级为 C，因为个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
            f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量、题材联动或数据完整性不足，"
            f"暂时只能作为观察对象；{seal_text}。"
        )
    if grade == "B":
        return (
            f"评级为 B，因为个股当前涨幅达到 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
            f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，同题材候选数为 {theme_count}，具备观察价值；"
            f"盘口质量评分为 {orderbook_quality:.1f}，{seal_text}；但真实委托排队位置和历史溢价数据仍未接入，"
            "不能提高到 A。"
        )
    return (
        f"评级为 A，因为市场闸门允许进攻，个股涨幅为 {change_pct:.2f}%，五分钟涨速为 "
        f"{five_min_speed_pct:.2f}%，资金净流入占比为 {big_order_net_inflow_ratio:.2%}，"
        f"盘口质量评分为 {orderbook_quality:.1f}，同题材候选数为 {theme_count}，且{seal_text}；"
        "仍需在实盘时继续核验数据时效和封单稳定性。"
    )


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
