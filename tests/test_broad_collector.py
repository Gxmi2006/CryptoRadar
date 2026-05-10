from __future__ import annotations

from app.binance.symbol_service import SymbolService
from app.collector.broad_market_collector import BroadMarketCollector, classify_data_quality, should_fetch_symbol_candles


class FakeBroadRest:
    def __init__(self) -> None:
        self.kline_calls: list[str] = []

    def get_exchange_info(self) -> dict:
        return {
            "symbols": [
                {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "LOWUSDT", "baseAsset": "LOW", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "MISSUSDT", "baseAsset": "MISS", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "OLDUSDT", "baseAsset": "OLD", "quoteAsset": "USDT", "status": "BREAK", "isSpotTradingAllowed": True},
            ]
        }

    def get_24hr_tickers(self) -> list[dict]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "20000000", "lastPrice": "80000", "priceChangePercent": "2", "highPrice": "81000", "lowPrice": "78000"},
            {"symbol": "LOWUSDT", "quoteVolume": "500", "lastPrice": "0.02", "priceChangePercent": "4", "highPrice": "0.03", "lowPrice": "0.01"},
            {"symbol": "MISSUSDT", "quoteVolume": "2000000", "lastPrice": "1", "priceChangePercent": "0", "highPrice": "1.1", "lowPrice": "0.9"},
        ]

    def get_klines(self, symbol: str, interval: str, limit: int = 24) -> list[list]:
        self.kline_calls.append(symbol)
        if symbol == "MISSUSDT":
            raise RuntimeError("no candles")
        return [[index, "1", "1.1", "0.9", str(1 + index / 100), "100", index + 1, "1000", "5"] for index in range(limit)]


def test_broad_collector_includes_low_volume_symbols(config: dict, db) -> None:
    config["binance"]["min_24h_volume_usdt"] = 5_000_000
    config["collector"]["min_24h_volume_usdt"] = 0
    rest = FakeBroadRest()
    summary = BroadMarketCollector(config, db, rest).collect_now()
    assert summary["collected"] == 3
    assert summary["fetch_candles"] == "auto"
    assert "BTCUSDT" in rest.kline_calls
    assert "LOWUSDT" not in rest.kline_calls

    low = db.query_one("SELECT * FROM symbol_data_quality WHERE symbol='LOWUSDT'")
    assert low is not None
    assert low["data_quality"] == "low_volume"

    live_symbols = SymbolService(FakeBroadRest(), db, config).discover_symbols()
    assert [row["symbol"] for row in live_symbols] == ["BTCUSDT"]


def test_missing_candles_are_labeled_instead_of_dropped(config: dict, db) -> None:
    config["collector"]["fetch_candles"] = True
    BroadMarketCollector(config, db, FakeBroadRest()).collect_now()
    missing = db.query_one("SELECT * FROM symbol_data_quality WHERE symbol='MISSUSDT'")
    assert missing is not None
    assert missing["data_quality"] == "missing_candles"
    saved = db.query_one("SELECT COUNT(*) AS count FROM candles WHERE symbol='BTCUSDT' AND interval=?", (config["collector"]["candle_interval"],))
    assert saved is not None
    assert saved["count"] == config["collector"]["candle_limit"]
    report = BroadMarketCollector(config, db, FakeBroadRest()).coverage_report()
    assert "MISSUSDT" in report


def test_data_quality_classification() -> None:
    assert classify_data_quality(price=1, volume_usdt=10_000_000, candle_count=24)[0] == "good"
    assert classify_data_quality(price=1, volume_usdt=2_000_000, candle_count=24)[0] == "thin"
    assert classify_data_quality(price=1, volume_usdt=500, candle_count=24)[0] == "low_volume"
    assert classify_data_quality(price=1, volume_usdt=5_000_000, candle_count=0)[0] == "missing_candles"
    assert classify_data_quality(price=1, volume_usdt=5_000_000, candle_count=0, candles_required=False)[0] == "good"


def test_collect_now_prints_progress(config: dict, db) -> None:
    messages: list[str] = []
    BroadMarketCollector(config, db, FakeBroadRest()).collect_now(messages.append)
    assert any("Loading Binance" in message for message in messages)
    assert any("Saving" in message for message in messages)


def test_auto_candle_policy_prioritizes_important_and_liquid_symbols() -> None:
    assert should_fetch_symbol_candles("auto", "LOWUSDT", 500, {"LOWUSDT"}, 999, 1, 5_000_000)
    assert should_fetch_symbol_candles("auto", "BTCUSDT", 20_000_000, set(), 0, 10, 5_000_000)
    assert not should_fetch_symbol_candles("auto", "LOWUSDT", 500, set(), 0, 10, 5_000_000)
    assert not should_fetch_symbol_candles("auto", "MIDUSDT", 10_000_000, set(), 10, 10, 5_000_000)
    assert should_fetch_symbol_candles("all", "ANYUSDT", 0, set(), 999, 1, 5_000_000)
    assert not should_fetch_symbol_candles("false", "BTCUSDT", 20_000_000, {"BTCUSDT"}, 0, 10, 5_000_000)
