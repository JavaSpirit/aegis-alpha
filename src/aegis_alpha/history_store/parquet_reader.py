from __future__ import annotations

import pathlib
from typing import Any


class MinuteBarReader:
    """Read minute bars from Parquet via DuckDB for date-range queries."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = pathlib.Path(root_dir)
        self._minute_dir = self.root_dir / "minute_bars"

    def read_minute_bars(
        self, *, symbol: str, start_day: str, end_day: str
    ) -> list[dict[str, Any]]:
        symbol_dir = self._minute_dir / symbol
        if not symbol_dir.exists():
            return []

        # Filter Parquet files by filename (stem = trading_day) in Python,
        # then read with DuckDB. This avoids DuckDB regex version differences.
        files: list[str] = []
        for path in sorted(symbol_dir.glob("*.parquet")):
            day = path.stem  # e.g. "2026-06-01"
            if start_day <= day <= end_day:
                files.append(str(path))

        if not files:
            return []

        import duckdb

        con = None
        try:
            con = duckdb.connect()
            unions = []
            params: list[str] = []
            for f in files:
                day = pathlib.Path(f).stem
                unions.append(
                    f"SELECT time, last_price, volume, average_price, ? AS trading_day "
                    f"FROM read_parquet('{f}')"
                )
                params.append(day)
            query = " UNION ALL ".join(unions) + " ORDER BY trading_day, time"
            rows = con.execute(query, params).fetchall()
            cols = ["time", "last_price", "volume", "average_price", "trading_day"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
