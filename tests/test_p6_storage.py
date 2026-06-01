from aegis_alpha.models import SuspendedStock
from aegis_alpha.storage import AegisAlphaStore


def test_save_and_list_suspended_stocks(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "p6.db"))
    store.init_db()

    a = SuspendedStock(
        symbol="600519", name="A", suspension_start_day="2026-05-25",
        suspension_end_day="", reason="重大事项",
    )
    b = SuspendedStock(
        symbol="000001", name="B", suspension_start_day="2026-05-26",
        suspension_end_day="2026-05-28", reason="重大资产重组",
    )
    store.save_suspended_stock(a, created_at="t1")
    store.save_suspended_stock(b, created_at="t2")

    rows = store.list_suspended_stocks(trading_day="2026-05-26")
    symbols = {r.symbol for r in rows}
    # A 仍处于停牌（end_day 为空）；B 在 2026-05-26 也是停牌
    assert symbols == {"600519", "000001"}

    rows_after = store.list_suspended_stocks(trading_day="2026-05-29")
    # B 已复牌（2026-05-28 截止）；A 仍未复牌
    after_symbols = {r.symbol for r in rows_after}
    assert after_symbols == {"600519"}
