def test_dragon_tiger_record_minimal_construct():
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat

    seat = DragonTigerSeat(
        seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
        seat_type="hot_money_known",
        hot_money_alias="章盟主",
        buy_amount_cny=12_000_000.0,
        sell_amount_cny=2_000_000.0,
        net_amount_cny=10_000_000.0,
    )
    record = DragonTigerRecord(
        symbol="600519",
        name="贵州茅台",
        trading_day="2026-05-30",
        list_reason="日涨幅偏离值达 7%",
        total_buy_cny=50_000_000.0,
        total_sell_cny=20_000_000.0,
        net_amount_cny=30_000_000.0,
        seats=[seat],
        provider="mock",
        data_mode="mock",
        created_at="2026-05-30T15:30:00+08:00",
    )
    assert record.symbol == "600519"
    assert record.seats[0].hot_money_alias == "章盟主"
    assert record.seats[0].seat_type == "hot_money_known"


def test_p6_market_event_types_extended():
    from aegis_alpha.models import MarketEventType
    from typing import get_args

    types = set(get_args(MarketEventType))
    assert "THEME_LEADER_BREAK_BOARD" in types
    assert "SECTOR_ROTATION" in types
    # 旧值不动
    assert "THEME_DIVERGENCE" in types
    assert "MARKET_BOTTOM_REVERSAL" in types


def test_sector_rotation_evidence_model_construct():
    from aegis_alpha.models import SectorRotationEvidence

    ev = SectorRotationEvidence(
        weakening_theme="军工",
        weakening_leader_status="broken",
        strengthening_theme="AI",
        strengthening_leader_status="sealed",
        weakening_alive_count=0,
        strengthening_alive_count=4,
    )
    assert ev.weakening_theme == "军工"
    assert ev.strengthening_alive_count == 4
