from __future__ import annotations

import math
import random
from typing import Any


class MockMarket:
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "MEMEUSDT", "RANGEUSDT", "DUMPUSDT", "BREAKUSDT"]

    def snapshots(self) -> dict[str, dict[str, Any]]:
        return {
            "BTCUSDT": self._snapshot("BTCUSDT", 80250, 1.8, 25_000_000_000),
            "ETHUSDT": self._snapshot("ETHUSDT", 3700, 1.2, 12_000_000_000),
            "SOLUSDT": self._snapshot("SOLUSDT", 145, 7.2, 800_000_000),
            "MEMEUSDT": self._snapshot("MEMEUSDT", 0.018, 28.0, 1_200_000),
            "RANGEUSDT": self._snapshot("RANGEUSDT", 2.4, 0.5, 40_000_000),
            "DUMPUSDT": self._snapshot("DUMPUSDT", 0.72, -9.4, 60_000_000),
            "BREAKUSDT": self._snapshot("BREAKUSDT", 12.8, 5.8, 120_000_000),
        }

    def _snapshot(self, symbol: str, price: float, change_24h: float, volume: float) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "price": price,
            "change_1h": change_24h / 5,
            "change_4h": change_24h / 2,
            "change_24h": change_24h,
            "volume_usdt": volume,
            "high_24h": price * (1 + abs(change_24h) / 100),
            "low_24h": price * (1 - abs(change_24h) / 150),
            "payload": {"mock": True},
        }

    def candles(self, symbol: str) -> dict[str, list[dict[str, float]]]:
        return {
            "5m": self._candles(symbol, 220, 0.16),
            "15m": self._candles(symbol, 220, 0.25),
            "1h": self._candles(symbol, 220, 0.45),
            "4h": self._candles(symbol, 220, 0.7),
            "1d": self._candles(symbol, 220, 1.0),
        }

    def _candles(self, symbol: str, count: int, volatility: float) -> list[dict[str, float]]:
        base = self.snapshots()[symbol]["price"]
        trend = {
            "SOLUSDT": 0.0018,
            "BREAKUSDT": 0.0014,
            "MEMEUSDT": 0.004,
            "DUMPUSDT": -0.0022,
            "BTCUSDT": 0.0004,
            "ETHUSDT": 0.0003,
        }.get(symbol, 0.0001)
        candles: list[dict[str, float]] = []
        price = base * (1 - trend * count / 2)
        for index in range(count):
            wave = math.sin(index / 8) * volatility / 100
            price *= 1 + trend + wave / 10
            if symbol == "BREAKUSDT" and index > count - 6:
                price *= 1.006
            if symbol == "MEMEUSDT" and index > count - 5:
                price *= 1.025
            if symbol == "DUMPUSDT" and index > count - 8:
                price *= 0.988
            open_price = price * (1 - wave / 2)
            close = price
            high = max(open_price, close) * (1 + volatility / 180)
            low = min(open_price, close) * (1 - volatility / 180)
            volume = 1000 + index * 3
            if index > count - 5 and symbol in {"SOLUSDT", "MEMEUSDT", "DUMPUSDT", "BREAKUSDT"}:
                volume *= 3.5
            candles.append(
                {
                    "open_time": index,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "quote_volume": volume * close,
                    "close_time": index + 1,
                }
            )
        return candles
