import pytest

from aegis_alpha.history_store import is_history_store_available

if not is_history_store_available():
    pytest.skip("pyarrow / duckdb not installed", allow_module_level=True)


def test_minute_bar_writer_writes_one_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars = [
        {"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0},
        {"time": "09:31:00", "last_price": 100.5, "volume": 800.0, "average_price": 100.2},
    ]
    path = writer.write_minute_bars(
        symbol="600519", trading_day="2026-06-01", bars=bars,
    )
    import pathlib
    assert pathlib.Path(path).exists()
    assert "600519" in path
    assert "2026-06-01" in path


def test_minute_bar_writer_overwrites_existing_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars1 = [{"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0}]
    bars2 = [{"time": "09:30:00", "last_price": 105.0, "volume": 2000.0, "average_price": 105.0}]
    writer.write_minute_bars(symbol="X", trading_day="2026-06-01", bars=bars1)
    path = writer.write_minute_bars(symbol="X", trading_day="2026-06-01", bars=bars2)

    import pyarrow.parquet as pq
    table = pq.read_table(path)
    assert table.num_rows == 1
    last_price = table.column("last_price")[0].as_py()
    assert abs(last_price - 105.0) < 1e-9
