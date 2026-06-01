from __future__ import annotations

import pathlib
from typing import Any


class MinuteBarWriter:
    """Write minute bars to Parquet partitioned by symbol/trading_day.

    Layout: {root_dir}/minute_bars/{symbol}/{trading_day}.parquet
    """

    def __init__(self, root_dir: str) -> None:
        self.root_dir = pathlib.Path(root_dir)
        self._minute_dir = self.root_dir / "minute_bars"

    def _partition_path(self, symbol: str, trading_day: str) -> pathlib.Path:
        return self._minute_dir / symbol / f"{trading_day}.parquet"

    def write_minute_bars(
        self,
        *,
        symbol: str,
        trading_day: str,
        bars: list[dict[str, Any]],
    ) -> str:
        """Overwrite the (symbol, trading_day) partition with the given bars.
        Returns the absolute filepath of the written Parquet file.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self._partition_path(symbol, trading_day)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not bars:
            schema = pa.schema(
                [
                    ("time", pa.string()),
                    ("last_price", pa.float64()),
                    ("volume", pa.float64()),
                    ("average_price", pa.float64()),
                ]
            )
            table = pa.Table.from_pylist([], schema=schema)
        else:
            normalized = [
                {
                    "time": str(b.get("time", "")),
                    "last_price": float(b.get("last_price", 0.0)),
                    "volume": float(b.get("volume", 0.0)),
                    "average_price": float(b.get("average_price", 0.0)),
                }
                for b in bars
            ]
            table = pa.Table.from_pylist(normalized)
        pq.write_table(table, str(path))
        return str(path)
