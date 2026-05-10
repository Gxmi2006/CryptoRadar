from __future__ import annotations

import asyncio

from app.alerts.coin_alerts import CoinAlertService, detect_coin_events, format_coin_alert, normalize_coin_id
from app.scheduler import CryptoRadarService


class FakeCoinRest:
    def get_exchange_info(self) -> dict:
        return {
            "symbols": [
                {"symbol": "SOLUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
                {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True},
            ]
        }

    def get_24hr_tickers(self) -> list[dict]:
        return [
            {
                "symbol": "SOLUSDT",
                "lastPrice": "124",
                "priceChangePercent": "24",
                "quoteVolume": "250000000",
                "highPrice": "125",
                "lowPrice": "96",
            }
        ]

    def get_klines(self, symbol: str, interval: str, limit: int = 96) -> list[list]:
        del symbol, interval
        rows = []
        price = 100.0
        for index in range(limit):
            volume = 1000 if index < limit - 1 else 5000
            close = price * (1.002 if index < limit - 4 else 1.02)
            rows.append([index, str(price), str(close * 1.01), str(price * 0.99), str(close), str(volume), index + 1, "1000", "5"])
            price = close
        return rows


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_text(self, message: str, signal=None) -> bool:
        del signal
        self.messages.append(message)
        return True


class FakeAlpha:
    def resolve_token(self, coin_id: str) -> dict | None:
        if coin_id.upper() == "FOREST":
            return {"symbol": "FOREST", "alphaId": "ALPHA_348", "tradeSymbol": "ALPHA_348USDT"}
        return None

    def get_ticker(self, trade_symbol: str) -> dict:
        assert trade_symbol == "ALPHA_348USDT"
        return {
            "symbol": trade_symbol,
            "lastPrice": "0.18",
            "priceChangePercent": "22",
            "quoteVolume": "1500000",
            "highPrice": "0.25",
            "lowPrice": "0.13",
        }

    def get_klines(self, trade_symbol: str, interval: str, limit: int = 96) -> list[dict]:
        del trade_symbol, interval
        return [
            {
                "open_time": index,
                "open": 0.14 + index / 10000,
                "high": 0.15 + index / 10000,
                "low": 0.13 + index / 10000,
                "close": 0.14 + index / 10000,
                "volume": 1000,
                "close_time": index + 1,
            }
            for index in range(limit)
        ]


class FakeCoinML:
    @staticmethod
    def predict_for_signal(signal: dict) -> dict:
        del signal
        return {
            "success_probability": 0.72,
            "risk_score": 0.31,
            "confidence_score": 0.48,
            "data_quality": "good",
            "model_version": "test",
        }


def test_coin_id_resolves_to_symbol_and_sends_message(config: dict, db) -> None:
    notifier = FakeNotifier()
    service = CoinAlertService(config, db, FakeCoinRest(), notifier)

    alert = service.check_coin("sol", force=True)

    assert alert["symbol"] == "SOLUSDT"
    assert alert["sent"] is True
    assert "COIN ALERT - SOLUSDT" in alert["message"]
    assert "SURGE" in alert["message"]
    assert notifier.messages


def test_coin_alert_supports_full_symbol_and_cleaning(config: dict, db) -> None:
    service = CoinAlertService(config, db, FakeCoinRest(), FakeNotifier())
    assert normalize_coin_id(" sol/usdt ") == "SOLUSDT"
    assert service.resolve_symbol("SOLUSDT") == "SOLUSDT"


def test_coin_alert_falls_back_to_binance_alpha(config: dict, db) -> None:
    service = CoinAlertService(config, db, FakeCoinRest(), FakeNotifier(), alpha=FakeAlpha())
    alert = service.check_coin("FOREST", force=True)
    assert alert["symbol"] == "ALPHA_348USDT"
    assert alert["source"] == "alpha"
    assert "FOREST (ALPHA_348USDT)" in alert["message"]


def test_preferred_coin_alert_includes_ml_breakout_note(config: dict, db) -> None:
    notifier = FakeNotifier()
    service = CoinAlertService(config, db, FakeCoinRest(), notifier)
    service.ml = FakeCoinML()

    alert = service.check_coin("SOL", force=True, preferred=True)

    assert any(event["type"] == "ML_BREAKOUT" for event in alert["events"])
    assert "🧠 ML breakout:" in alert["message"]
    assert "72% success probability" in alert["message"]


def test_coin_event_detection_covers_surge_dump_and_risk(config: dict) -> None:
    events = detect_coin_events(
        price=124,
        high_24h=125,
        low_24h=96,
        change_24h=24,
        change_1h=5,
        change_4h=8,
        relative_volume=2.4,
        rsi=82,
        cfg=config["coin_alerts"],
    )
    types = {event["type"] for event in events}
    assert {"SURGE", "FAST_MOVE_UP", "VOLUME_SPIKE", "HIGH_RISK_PUMP"}.issubset(types)

    dump_events = detect_coin_events(
        price=90,
        high_24h=110,
        low_24h=89,
        change_24h=-12,
        change_1h=-5,
        change_4h=-7,
        relative_volume=1,
        rsi=35,
        cfg=config["coin_alerts"],
    )
    dump_types = {event["type"] for event in dump_events}
    assert {"DUMP", "FAST_MOVE_DOWN", "NEAR_24H_LOW"}.issubset(dump_types)


def test_format_coin_alert_includes_final_safety_note() -> None:
    text = format_coin_alert(
        {
            "symbol": "SOLUSDT",
            "price": 124,
            "change_24h": 24,
            "change_1h": 5,
            "change_4h": 8,
            "volume_usdt": 250000000,
            "relative_volume": 2.4,
            "rsi": 82,
            "events": [{"type": "SURGE", "text": "Price is up 24.00% in 24h."}],
        }
    )
    assert "This is an analysis-based alert, not guaranteed profit. Decide manually." in text

    near_high = format_coin_alert(
        {
            "symbol": "SOLUSDT",
            "price": 124,
            "change_24h": 1,
            "change_1h": 0.5,
            "change_4h": 1,
            "volume_usdt": 250000000,
            "relative_volume": 1.1,
            "events": [{"type": "NEAR_24H_HIGH", "text": "Price is within 2.0% of the 24h high."}],
        }
    )
    assert "breakout continuation or rejection" in near_high


def test_auto_pipeline_run_once_checks_watchlist_coin_alerts(config: dict, db, tmp_path) -> None:
    config["automation"]["collect_market_data"] = False
    config["automation"]["scan_market"] = False
    config["automation"]["auto_train_ml"] = False
    config["binance"]["watchlist_symbols"] = ["SOLUSDT"]
    service = CryptoRadarService(config, db, tmp_path, mock=True)

    class FakeCoinAlerts:
        def check_watchlist(self):
            return [{"symbol": "SOLUSDT", "events": [{"type": "SURGE"}], "sent": True}]

    service.coin_alerts = FakeCoinAlerts()
    messages: list[str] = []

    asyncio.run(service.run_auto_pipeline(run_once=True, status=messages.append))

    assert any("Watchlist coin alerts checked" in message for message in messages)
