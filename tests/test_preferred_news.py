from __future__ import annotations

from app.alerts.coin_alerts import CoinAlertService
from app.news.preferred_news import PreferredNewsService, parse_rss_items, score_news_item, symbol_aliases
from app.storage.user_lists import UserListStore


RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Crypto Test Feed</title>
    <item>
      <title>Forest token gets Binance Alpha listing and partnership</title>
      <link>https://example.test/forest-binance-alpha</link>
      <pubDate>Sun, 10 May 2026 08:00:00 GMT</pubDate>
      <description>FOREST gains attention after Binance Alpha listing news.</description>
    </item>
    <item>
      <title>Solana network outage worries traders</title>
      <link>https://example.test/sol-outage</link>
      <pubDate>Sun, 10 May 2026 07:00:00 GMT</pubDate>
      <description>SOL traders watch downside risk.</description>
    </item>
  </channel>
</rss>
"""


class FakeRest:
    def get_exchange_info(self) -> dict:
        return {"symbols": [{"symbol": "SOLUSDT", "status": "TRADING", "isSpotTradingAllowed": True}]}

    def get_24hr_tickers(self) -> list[dict]:
        return [
            {
                "symbol": "SOLUSDT",
                "lastPrice": "150",
                "priceChangePercent": "-4",
                "quoteVolume": "200000000",
                "highPrice": "158",
                "lowPrice": "145",
            }
        ]

    def get_klines(self, symbol: str, interval: str, limit: int = 96) -> list[list]:
        del symbol, interval
        return [[i, "100", "101", "99", str(100 + i * 0.1), "1000", i + 1, "1000", "4"] for i in range(limit)]


class FakeAlpha:
    def resolve_token(self, coin_id: str) -> dict | None:
        if coin_id.upper() in {"FOREST", "ALPHA_348USDT"}:
            return {"symbol": "FOREST", "name": "Forest", "alphaId": "ALPHA_348", "tradeSymbol": "ALPHA_348USDT"}
        return None

    def get_ticker(self, trade_symbol: str) -> dict:
        del trade_symbol
        return {
            "lastPrice": "0.18",
            "priceChangePercent": "12.4",
            "quoteVolume": "3500000",
            "highPrice": "0.19",
            "lowPrice": "0.13",
        }

    def get_klines(self, trade_symbol: str, interval: str, limit: int = 96) -> list[dict]:
        del trade_symbol, interval
        return [
            {
                "open_time": i,
                "open": 0.1,
                "high": 0.2,
                "low": 0.09,
                "close": 0.1 + i * 0.001,
                "volume": 1000,
                "close_time": i + 1,
            }
            for i in range(limit)
        ]


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_text(self, message: str, signal=None) -> bool:
        del signal
        self.messages.append(message)
        return True


class FakeML:
    @staticmethod
    def predict_for_signal(signal: dict) -> dict:
        del signal
        return {
            "success_probability": 0.67,
            "risk_score": 0.38,
            "confidence_score": 0.55,
            "data_quality": "thin",
            "model_version": "test",
        }


def test_rss_parsing_from_fixture_without_network() -> None:
    items = parse_rss_items(RSS_FIXTURE, "Fixture")
    assert len(items) == 2
    assert items[0].title == "Forest token gets Binance Alpha listing and partnership"
    assert items[0].source == "Fixture"


def test_news_matching_scores_binance_alpha_coin(config: dict, db) -> None:
    config["news"]["enabled"] = True
    market = {"source": "alpha", "symbol": "ALPHA_348USDT", "token": {"symbol": "FOREST", "name": "Forest"}}
    item = {
        "id": "news-1",
        "source": "Fixture",
        "title": "Forest token gets Binance Alpha listing and partnership",
        "link": "https://example.test/forest",
        "published_at": "2026-05-10T08:00:00+00:00",
        "summary": "FOREST gains attention.",
    }
    scored = score_news_item(item, symbol_aliases(market))
    assert scored["importance_score"] >= 70
    assert scored["sentiment"] == "bullish"


def test_preferred_news_sends_once_and_includes_ml_note(config: dict, db) -> None:
    config["news"]["enabled"] = True
    config["news"]["sources"] = [{"name": "Fixture", "url": "https://example.test/rss"}]
    notifier = FakeNotifier()
    coin_alerts = CoinAlertService(config, db, FakeRest(), notifier, alpha=FakeAlpha())
    coin_alerts.ml = FakeML()
    service = PreferredNewsService(config, db, coin_alerts, notifier, fetcher=lambda url: RSS_FIXTURE)
    UserListStore(db).add_preferred("ALPHA_348USDT")

    first = service.check_preferred_news()
    second = service.check_preferred_news()

    assert first[0]["sent"] is True
    assert second[0]["sent"] is False
    assert len(notifier.messages) == 1
    assert "📰 FOREST" in notifier.messages[0]
    assert "67% success probability" in notifier.messages[0]
    assert "Not guaranteed profit. Decide manually." in notifier.messages[0]


def test_news_summary_handles_no_matching_news(config: dict, db) -> None:
    config["news"]["enabled"] = True
    config["news"]["sources"] = [{"name": "Fixture", "url": "https://example.test/rss"}]
    notifier = FakeNotifier()
    coin_alerts = CoinAlertService(config, db, FakeRest(), notifier, alpha=FakeAlpha())
    service = PreferredNewsService(config, db, coin_alerts, notifier, fetcher=lambda url: RSS_FIXTURE)

    text = service.format_coin_news_summary("SOL")

    assert "SOLUSDT" in text
    assert "Solana network outage" in text
    assert "Analysis-only alert" in text
