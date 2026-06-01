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


def test_list_suspended_stocks_uses_sql_filter_for_trading_day(tmp_path):
    """SQL filter must respect: start <= day AND (end blank OR end >= day).

    This test exercises the SQL path with mixed entries to make sure the
    optimization does not break the existing filter semantics.
    """
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "p7.db"))
    store.init_db()
    store.save_suspended_stock(
        SuspendedStock(symbol="A", suspension_start_day="2026-05-20",
                       suspension_end_day=""),
        created_at="t",
    )
    store.save_suspended_stock(
        SuspendedStock(symbol="B", suspension_start_day="2026-05-22",
                       suspension_end_day="2026-05-26"),
        created_at="t",
    )
    store.save_suspended_stock(
        SuspendedStock(symbol="C", suspension_start_day="2026-06-01",
                       suspension_end_day=""),
        created_at="t",
    )
    rows = store.list_suspended_stocks(trading_day="2026-05-25")
    symbols = {r.symbol for r in rows}
    # A is open-ended after 2026-05-20 → in. B starts 22 ends 26 → in (25 <= 26). C starts 06-01 → out.
    assert symbols == {"A", "B"}

    rows_after = store.list_suspended_stocks(trading_day="2026-05-30")
    after_symbols = {r.symbol for r in rows_after}
    # B's end_day is 2026-05-26 < 2026-05-30 → out. A still open-ended → in. C still future → out.
    assert after_symbols == {"A"}
