import pytest

from aegis_alpha.history_store import is_history_store_available

if not is_history_store_available():
    pytest.skip("pyarrow / duckdb not installed", allow_module_level=True)


def test_minute_bar_reader_returns_rows_for_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter
    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars = [
        {"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0},
        {"time": "09:31:00", "last_price": 100.5, "volume": 800.0, "average_price": 100.2},
    ]
    writer.write_minute_bars(symbol="600519", trading_day="2026-06-01", bars=bars)

    reader = MinuteBarReader(root_dir=str(tmp_path))
    rows = reader.read_minute_bars(
        symbol="600519", start_day="2026-06-01", end_day="2026-06-01"
    )
    assert len(rows) == 2
    assert rows[0]["time"] == "09:30:00"


def test_minute_bar_reader_returns_empty_for_missing_partition(tmp_path):
    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    reader = MinuteBarReader(root_dir=str(tmp_path))
    rows = reader.read_minute_bars(
        symbol="ZZZ", start_day="2026-06-01", end_day="2026-06-01"
    )
    assert rows == []
