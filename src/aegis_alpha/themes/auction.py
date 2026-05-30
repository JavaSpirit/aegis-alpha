from __future__ import annotations

from aegis_alpha.models import AuctionAnalysis, AuctionPattern


class AuctionAnalyzer:
    def analyze(
        self,
        *,
        symbol: str,
        trading_day: str,
        auction_change_pct: float = 0.0,
        auction_turnover_cny: float = 0.0,
        auction_turnover_rate: float = 0.0,
        pre_open_change_pct: float = 0.0,
        final_open_change_pct: float = 0.0,
        cancellation_rate: float = 0.0,
    ) -> AuctionAnalysis:
        pattern, reason = classify_auction_pattern(
            auction_change_pct=auction_change_pct,
            auction_turnover_rate=auction_turnover_rate,
            cancellation_rate=cancellation_rate,
        )
        return AuctionAnalysis(
            symbol=symbol,
            trading_day=trading_day,
            auction_change_pct=auction_change_pct,
            auction_turnover_cny=auction_turnover_cny,
            auction_turnover_rate=auction_turnover_rate,
            pattern=pattern,
            pattern_reason=reason,
            pre_open_change_pct=pre_open_change_pct,
            final_open_change_pct=final_open_change_pct,
            cancellation_rate=cancellation_rate,
        )


def classify_auction_pattern(
    *,
    auction_change_pct: float,
    auction_turnover_rate: float,
    cancellation_rate: float = 0.0,
) -> tuple[AuctionPattern, str]:
    if auction_change_pct <= -1.0:
        return "weak_open", "Auction opened weak below -1%."
    if auction_change_pct >= 5.0 and (auction_turnover_rate >= 5.0 or cancellation_rate >= 0.45):
        return "exit_liquidity", "High auction open with heavy turnover/cancellations."
    if auction_change_pct >= 2.0 and auction_turnover_rate >= 1.0 and cancellation_rate < 0.35:
        return "strong_open", "Auction showed positive open with controlled cancellation pressure."
    if auction_change_pct or auction_turnover_rate:
        return "stable", "Auction signal is present but not extreme."
    return "unknown", "Auction data is unavailable."
