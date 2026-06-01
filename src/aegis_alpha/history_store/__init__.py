"""P6 Parquet history store. Optional dependencies: pyarrow + duckdb."""

from __future__ import annotations


def is_history_store_available() -> bool:
    """Return True iff pyarrow and duckdb can be imported."""
    try:
        import pyarrow  # noqa: F401
        import duckdb  # noqa: F401
    except ImportError:
        return False
    return True


def history_store_unavailable_error() -> str:
    return (
        "history-store extras not installed: install with "
        "`pip install '.[history-store]'` "
        "(pyarrow + duckdb)."
    )
