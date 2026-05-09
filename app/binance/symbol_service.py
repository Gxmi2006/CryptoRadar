from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class SymbolService:
    def __init__(self, rest: Any, db: Any, config: dict[str, Any]):
        self.rest = rest
        self.db = db
        self.config = config
        self._cache: list[dict[str, Any]] = []
        self._cache_at: datetime | None = None

    def discover_symbols(self) -> list[dict[str, Any]]:
        refresh_hours = float(self.config["binance"].get("refresh_symbols_hours", 6))
        if self._cache and self._cache_at and datetime.now(timezone.utc) - self._cache_at < timedelta(hours=refresh_hours):
            return self._cache

        info = self.rest.get_exchange_info()
        tickers = {item["symbol"]: item for item in self.rest.get_24hr_tickers()}
        quote_assets = set(self.config["binance"].get("quote_assets", ["USDT"]))
        ignored = set(self.config["binance"].get("ignored_symbols", []))
        min_volume = float(self.config["binance"].get("min_24h_volume_usdt", 0))
        rows: list[dict[str, Any]] = []

        for item in info.get("symbols", []):
            symbol = item.get("symbol", "")
            quote = item.get("quoteAsset")
            ticker = tickers.get(symbol, {})
            quote_volume = float(ticker.get("quoteVolume") or 0)
            if quote not in quote_assets:
                continue
            if symbol in ignored:
                continue
            if item.get("status") != "TRADING":
                continue
            if item.get("isSpotTradingAllowed") is False:
                continue
            if quote_volume < min_volume:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "base_asset": item.get("baseAsset", ""),
                    "quote_asset": quote,
                    "status": item.get("status", ""),
                    "active": 1,
                    "volume_usdt": quote_volume,
                    "price": float(ticker.get("lastPrice") or 0),
                    "change_24h": float(ticker.get("priceChangePercent") or 0),
                }
            )

        rows.sort(key=lambda row: row["volume_usdt"], reverse=True)
        self.db.executemany(
            """
            INSERT INTO symbols(symbol, base_asset, quote_asset, status, active, volume_usdt, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                base_asset=excluded.base_asset,
                quote_asset=excluded.quote_asset,
                status=excluded.status,
                active=excluded.active,
                volume_usdt=excluded.volume_usdt,
                last_seen=CURRENT_TIMESTAMP
            """,
            (
                (row["symbol"], row["base_asset"], row["quote_asset"], row["status"], row["active"], row["volume_usdt"])
                for row in rows
            ),
        )
        self._cache = rows
        self._cache_at = datetime.now(timezone.utc)
        return rows

    def select_symbols(self, symbols: list[dict[str, Any]]) -> list[str]:
        mode = self.config["binance"].get("monitoring_mode", "high_volume")
        limit = int(self.config["binance"].get("max_symbols_to_analyze", 150))
        priority = list(dict.fromkeys(self.config["binance"].get("priority_symbols", [])))
        watchlist = list(dict.fromkeys(self.config["binance"].get("watchlist_symbols", [])))
        new_listings = list(dict.fromkeys(self.config["binance"].get("newly_listed_symbols", [])))
        available = {row["symbol"] for row in symbols}

        selected: list[str] = [symbol for symbol in priority if symbol in available]
        if mode == "watchlist_only":
            selected.extend(symbol for symbol in watchlist if symbol in available)
        elif mode == "new_listings":
            selected.extend(symbol for symbol in new_listings if symbol in available)
        else:
            selected.extend(row["symbol"] for row in symbols)
        return list(dict.fromkeys(selected))[:limit]

    def market_snapshots(self, selected_symbols: list[str]) -> dict[str, dict[str, Any]]:
        tickers = {item["symbol"]: item for item in self.rest.get_24hr_tickers()}
        snapshots: dict[str, dict[str, Any]] = {}
        for symbol in selected_symbols:
            ticker = tickers.get(symbol)
            if not ticker:
                continue
            snapshots[symbol] = {
                "symbol": symbol,
                "price": float(ticker.get("lastPrice") or 0),
                "change_1h": 0.0,
                "change_4h": 0.0,
                "change_24h": float(ticker.get("priceChangePercent") or 0),
                "volume_usdt": float(ticker.get("quoteVolume") or 0),
                "high_24h": float(ticker.get("highPrice") or 0),
                "low_24h": float(ticker.get("lowPrice") or 0),
                "payload": ticker,
            }
        return snapshots


def parse_exchange_symbol(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol", ""),
        "base_asset": item.get("baseAsset", ""),
        "quote_asset": item.get("quoteAsset", ""),
        "status": item.get("status", ""),
        "spot_allowed": bool(item.get("isSpotTradingAllowed", True)),
    }
