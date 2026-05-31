def test_save_and_get_dragon_tiger_record(tmp_path):
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "dt.db"))
    store.init_db()

    record = DragonTigerRecord(
        symbol="600519",
        name="贵州茅台",
        trading_day="2026-05-30",
        list_reason="日涨幅偏离 7%",
        total_buy_cny=20_000_000.0,
        total_sell_cny=5_000_000.0,
        net_amount_cny=15_000_000.0,
        seats=[
            DragonTigerSeat(
                seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
                seat_type="hot_money_known",
                hot_money_alias="章盟主",
                buy_amount_cny=12_000_000.0,
                sell_amount_cny=0.0,
                net_amount_cny=12_000_000.0,
            )
        ],
        provider="jvquant",
        data_mode="real",
        created_at="2026-05-30T15:30:00+08:00",
    )
    store.save_dragon_tiger(record)
    fetched = store.get_dragon_tiger("600519", "2026-05-30")
    assert fetched is not None
    assert fetched.net_amount_cny == 15_000_000.0
    assert fetched.seats[0].hot_money_alias == "章盟主"


def test_list_active_seats_today_aggregates_known_aliases(tmp_path):
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "dt2.db"))
    store.init_db()

    seat_a = DragonTigerSeat(
        seat_name="A", seat_type="hot_money_known", hot_money_alias="章盟主",
        buy_amount_cny=10_000_000.0, sell_amount_cny=0.0, net_amount_cny=10_000_000.0,
    )
    seat_b = DragonTigerSeat(
        seat_name="B", seat_type="hot_money_known", hot_money_alias="章盟主",
        buy_amount_cny=5_000_000.0, sell_amount_cny=0.0, net_amount_cny=5_000_000.0,
    )
    store.save_dragon_tiger(
        DragonTigerRecord(
            symbol="600519", name="贵州茅台", trading_day="2026-05-30",
            total_buy_cny=10_000_000.0, total_sell_cny=0.0, net_amount_cny=10_000_000.0,
            seats=[seat_a], provider="mock", data_mode="mock", created_at="t",
        )
    )
    store.save_dragon_tiger(
        DragonTigerRecord(
            symbol="000001", name="平安银行", trading_day="2026-05-30",
            total_buy_cny=5_000_000.0, total_sell_cny=0.0, net_amount_cny=5_000_000.0,
            seats=[seat_b], provider="mock", data_mode="mock", created_at="t",
        )
    )
    rows = store.list_active_seats_today("2026-05-30")
    aliases = {row["hot_money_alias"]: row for row in rows}
    assert "章盟主" in aliases
    assert aliases["章盟主"]["symbol_count"] == 2
    assert aliases["章盟主"]["total_net_buy_cny"] == 15_000_000.0


def test_save_and_list_contrarian_pool(tmp_path):
    from aegis_alpha.models import ContrarianPoolEntry
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "cp.db"))
    store.init_db()

    entry_a = ContrarianPoolEntry(
        symbol="000001", name="A", pool_kind="limit_down", trading_day="2026-05-30",
        consecutive_days=2, change_pct=-9.95, notes=["跌停"],
    )
    entry_b = ContrarianPoolEntry(
        symbol="000002", name="B", pool_kind="st", trading_day="2026-05-30",
        consecutive_days=0, change_pct=4.95, notes=["ST 涨停"],
    )
    store.save_contrarian_pool_entry(entry_a, created_at="t1")
    store.save_contrarian_pool_entry(entry_b, created_at="t2")

    limit_down = store.list_contrarian_pool("2026-05-30", pool_kind="limit_down")
    assert len(limit_down) == 1
    assert limit_down[0].symbol == "000001"

    everything = store.list_contrarian_pool("2026-05-30")
    assert {e.symbol for e in everything} == {"000001", "000002"}
