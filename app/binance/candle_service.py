from __future__ import annotations

from typing import Any

from app.binance.rest_client import parse_kline


class CandleService:
    def __init__(self, rest: Any):
        self.rest = rest

    def get_candles(self, symbol: str, interval: str, limit: int = 220) -> list[dict[str, float]]:
        rows = self.rest.get_klines(symbol=symbol, interval=interval, limit=limit)
        return [parse_kline(row) for row in rows]

    def get_multi_timeframe(self, symbol: str, timeframes: list[str], limit: int = 220) -> dict[str, list[dict[str, float]]]:
        data: dict[str, list[dict[str, float]]] = {}
        for timeframe in timeframes:
            data[timeframe] = self.get_candles(symbol, timeframe, limit=limit)
        return data
