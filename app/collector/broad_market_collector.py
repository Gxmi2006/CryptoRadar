from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.binance.rest_client import BinancePublicRestClient, parse_kline
from app.storage.collector_store import CollectorStore


class BroadMarketCollector:
    """Collect broad Binance Spot data without changing live alert filters."""

    def __init__(self, config: dict[str, Any], db: Any, rest: Any | None = None):
        self.config = config
        self.db = db
        self.rest = rest or BinancePublicRestClient()
        self.store = CollectorStore(db)

    def collect_now(self, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        cfg = self.config.get("collector", {})
        quote_assets = set(cfg.get("quote_assets") or self.config.get("binance", {}).get("quote_assets", ["USDT"]))
        min_volume = float(cfg.get("min_24h_volume_usdt", 0))
        limit = int(cfg.get("max_symbols_per_cycle", 1000))
        include_low_data = bool(cfg.get("include_low_data_symbols", True))
        fetch_mode = str(cfg.get("fetch_candles", "auto")).lower()
        candle_min_volume = float(cfg.get("candle_min_24h_volume_usdt", 5_000_000))
        max_candle_symbols = int(cfg.get("max_candle_symbols_per_cycle", 120))
        candle_interval = str(cfg.get("candle_interval", "1h"))
        candle_limit = int(cfg.get("candle_limit", 24))
        important_symbols = set(self.config.get("binance", {}).get("priority_symbols", []))
        important_symbols.update(self.config.get("binance", {}).get("watchlist_symbols", []))

        _progress(progress, "Loading Binance exchange info and 24h tickers...")
        info = self.rest.get_exchange_info()
        tickers = {item.get("symbol"): item for item in self.rest.get_24hr_tickers()}
        rows: list[dict[str, Any]] = []
        skipped = 0
        eligible = [
            item
            for item in info.get("symbols", [])
            if item.get("quoteAsset") in quote_assets
            and item.get("status") == "TRADING"
            and item.get("isSpotTradingAllowed") is not False
        ]
        _progress(progress, f"Found {len(eligible)} active Spot symbols for {', '.join(sorted(quote_assets))}.")

        candle_symbols_used = 0
        for item in eligible:
            symbol = item.get("symbol", "")
            ticker = tickers.get(symbol, {})
            volume = _float(ticker.get("quoteVolume"))
            if volume < min_volume and not include_low_data:
                skipped += 1
                continue
            should_fetch_candles = should_fetch_symbol_candles(
                fetch_mode=fetch_mode,
                symbol=symbol,
                volume_usdt=volume,
                important_symbols=important_symbols,
                candle_symbols_used=candle_symbols_used,
                max_candle_symbols=max_candle_symbols,
                candle_min_volume=candle_min_volume,
            )
            if should_fetch_candles:
                candle_symbols_used += 1
            rows.append(self._build_row(item, ticker, candle_interval, candle_limit, should_fetch_candles))
            if progress and (len(rows) == 1 or len(rows) % 50 == 0):
                _progress(progress, f"Prepared {len(rows)} symbols... candles fetched for {candle_symbols_used}.")
            if len(rows) >= limit:
                break

        _progress(progress, f"Saving {len(rows)} broad market snapshots with candles for {candle_symbols_used} symbols...")
        self.store.save_snapshots(rows)
        quality_counts: dict[str, int] = {}
        for row in rows:
            quality_counts[row["data_quality"]] = quality_counts.get(row["data_quality"], 0) + 1
        return {
            "collected": len(rows),
            "skipped": skipped,
            "quote_assets": sorted(quote_assets),
            "fetch_candles": fetch_mode,
            "candle_symbols": candle_symbols_used,
            "quality_counts": quality_counts,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def coverage_report(self) -> str:
        data = self.store.coverage_stats()
        lines = [
            "CryptoRadar Data Coverage Report",
            f"Generated at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"Total broad snapshots: {data['total_snapshots']}",
            f"Symbols with quality labels: {data['total_symbols']}",
            "",
            "Data quality:",
        ]
        for row in data["quality_counts"]:
            lines.append(f"- {row['data_quality']}: {row['count']}")
        lines.extend(["", "Lowest-volume symbols:"])
        for row in data["lowest_volume"]:
            lines.append(f"- {row['symbol']} volume={float(row['volume_usdt'] or 0):.2f} quality={row['data_quality']}")
        lines.extend(["", "Weak-data symbols:"])
        for row in data["weak_symbols"]:
            lines.append(f"- {row['symbol']} quality={row['data_quality']}")
        if not data["quality_counts"]:
            lines.append("- No broad collection data yet. Run python main.py --collect-market-data-now")
        return "\n".join(lines)

    def _build_row(
        self,
        item: dict[str, Any],
        ticker: dict[str, Any],
        candle_interval: str,
        candle_limit: int,
        fetch_candles: bool,
    ) -> dict[str, Any]:
        symbol = item.get("symbol", "")
        candles = self._safe_klines(symbol, candle_interval, candle_limit) if fetch_candles else []
        price = _float(ticker.get("lastPrice"))
        if price <= 0 and candles:
            price = candles[-1]["close"]
        change_1h, change_4h = _changes_from_candles(candles)
        volume = _float(ticker.get("quoteVolume"))
        quality, reasons = classify_data_quality(
            price=price,
            volume_usdt=volume,
            candle_count=len(candles),
            candles_required=fetch_candles,
        )
        payload = {
            "ticker": ticker,
            "candles_requested": fetch_candles,
            "candle_interval": candle_interval,
            "candle_count": len(candles),
            "recent_closes": [round(candle["close"], 10) for candle in candles[-8:]],
        }
        return {
            "symbol": symbol,
            "base_asset": item.get("baseAsset", ""),
            "quote_asset": item.get("quoteAsset", ""),
            "price": price,
            "change_1h": change_1h,
            "change_4h": change_4h,
            "change_24h": _float(ticker.get("priceChangePercent")),
            "volume_usdt": volume,
            "high_24h": _float(ticker.get("highPrice")),
            "low_24h": _float(ticker.get("lowPrice")),
            "data_quality": quality,
            "quality_reasons": reasons,
            "payload": payload,
            "candle_count": len(candles),
            "candle_interval": candle_interval,
            "candles": candles,
        }

    def _safe_klines(self, symbol: str, interval: str, limit: int) -> list[dict[str, float]]:
        try:
            raw = self.rest.get_klines(symbol, interval, limit=limit)
            return [parse_kline(item) for item in raw]
        except Exception:
            return []


def classify_data_quality(price: float, volume_usdt: float, candle_count: int, candles_required: bool = True) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if price <= 0:
        reasons.append("missing_price")
    if candles_required and candle_count == 0:
        reasons.append("missing_candles")
        return "missing_candles", reasons
    if not candles_required and candle_count == 0:
        reasons.append("candles_not_requested")
    if volume_usdt < 1_000_000:
        reasons.append("low_volume")
        return "low_volume", reasons
    if volume_usdt < 5_000_000 or (candles_required and candle_count < 12):
        if volume_usdt < 5_000_000:
            reasons.append("thin_volume")
        if candles_required and candle_count < 12:
            reasons.append("thin_candles")
        return "thin", reasons
    return "good", reasons


def should_fetch_symbol_candles(
    fetch_mode: str,
    symbol: str,
    volume_usdt: float,
    important_symbols: set[str],
    candle_symbols_used: int,
    max_candle_symbols: int,
    candle_min_volume: float,
) -> bool:
    if fetch_mode in {"false", "off", "no", "0"}:
        return False
    if fetch_mode in {"true", "on", "yes", "1", "all"}:
        return True
    if fetch_mode != "auto":
        return False
    if symbol in important_symbols:
        return True
    if candle_symbols_used >= max_candle_symbols:
        return False
    return volume_usdt >= candle_min_volume


def _changes_from_candles(candles: list[dict[str, float]]) -> tuple[float, float]:
    if not candles:
        return 0.0, 0.0
    last = candles[-1]["close"]
    one_hour = _change_pct(last, candles[-2]["close"]) if len(candles) >= 2 else 0.0
    four_hour = _change_pct(last, candles[-5]["close"]) if len(candles) >= 5 else 0.0
    return one_hour, four_hour


def _change_pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
