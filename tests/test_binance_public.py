from __future__ import annotations

from pathlib import Path

from app.binance.market_stream import parse_mini_ticker_event, parse_rolling_ticker_event
from app.binance.symbol_service import SymbolService


class FakeRest:
    def get_exchange_info(self) -> dict:
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "isSpotTradingAllowed": True,
                },
                {
                    "symbol": "OLDUSDT",
                    "baseAsset": "OLD",
                    "quoteAsset": "USDT",
                    "status": "BREAK",
                    "isSpotTradingAllowed": True,
                },
            ]
        }

    def get_24hr_tickers(self) -> list[dict]:
        return [
            {"symbol": "BTCUSDT", "quoteVolume": "10000000", "lastPrice": "80000", "priceChangePercent": "2.5"},
            {"symbol": "OLDUSDT", "quoteVolume": "10000000", "lastPrice": "1", "priceChangePercent": "0"},
        ]


def test_binance_symbol_discovery_filters_active_spot(config: dict, db) -> None:
    config["binance"]["min_24h_volume_usdt"] = 1_000
    symbols = SymbolService(FakeRest(), db, config).discover_symbols()
    assert [item["symbol"] for item in symbols] == ["BTCUSDT"]


def test_websocket_event_parsing() -> None:
    mini = parse_mini_ticker_event({"E": 1, "s": "BTCUSDT", "c": "100", "o": "95", "h": "101", "l": "94", "v": "5", "q": "500"})
    rolling = parse_rolling_ticker_event({"s": "BTCUSDT", "c": "110", "o": "100", "q": "1200"}, "1h")
    assert mini["symbol"] == "BTCUSDT"
    assert rolling["change_pct"] == 10


def test_no_execution_endpoint_strings_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = [
        "/api/v3/order",
        "/api/v3/account",
        "/sapi/",
        "create_order",
        "cancel_order",
        "withdraw",
        "transfer_funds",
    ]
    for token in forbidden:
        assert token not in source
