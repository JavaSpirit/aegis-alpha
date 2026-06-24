"""HTTP client for tdxmcp REST API.

Thin wrapper around requests to http://localhost:6999.
No dependency on pytdx — communicates purely over HTTP.
"""
from __future__ import annotations

import os
from typing import Any

import requests


def _base_url() -> str:
    return os.environ.get("TDXMCP_BASE_URL", "http://localhost:6999").rstrip("/")


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{_base_url()}{path}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, json_data: Any) -> Any:
    url = f"{_base_url()}{path}"
    resp = requests.post(url, json=json_data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def status() -> dict:
    return _get("/api/status")


def quote(symbol: str) -> dict:
    """symbol format: sh600519 / sz000001 / bj430047"""
    return _get(f"/api/quote/{symbol}")


def quotes(symbols: list[str]) -> list[dict]:
    """Batch quotes, symbols like ['sh600519','sz000001']. Returns list of raw quote dicts."""
    data = _post("/api/quotes", json_data=symbols)
    if isinstance(data, dict) and "quotes" in data:
        return data["quotes"]
    return data if isinstance(data, list) else []


def quotes_batch(symbols: list[str]) -> list[dict]:
    """Large batch quotes. Returns list of raw quote dicts."""
    data = _post("/api/quotes/batch", json_data=symbols)
    if isinstance(data, dict) and "quotes" in data:
        return data["quotes"]
    return data if isinstance(data, list) else []


def history(symbol: str, period: int = 4, start: str = "", count: int = 100) -> list[dict]:
    """K-line history. period: 4=daily, 8=1min"""
    params: dict[str, Any] = {"symbol": symbol, "period": period, "count": count}
    if start:
        params["start"] = start
    return _get(f"/api/history/{symbol}", params=params)


def blocks() -> list[dict]:
    data = _get("/api/blocks")
    if isinstance(data, dict) and "blocks" in data:
        return data["blocks"]
    return data if isinstance(data, list) else []


def industries() -> list[dict]:
    data = _get("/api/industries")
    if isinstance(data, dict) and "industries" in data:
        return data["industries"]
    return data if isinstance(data, list) else []


def finance(symbol: str) -> dict:
    return _get(f"/api/finance/{symbol}")


def stock_info(symbol: str) -> dict:
    return _get(f"/api/stock/{symbol}")


def markets() -> list[dict]:
    return _get("/api/markets")


def xdxr(symbol: str) -> list[dict]:
    return _get(f"/api/xdxr/{symbol}")
