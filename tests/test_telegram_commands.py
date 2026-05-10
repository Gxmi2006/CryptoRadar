from __future__ import annotations

from app.storage.user_lists import UserListStore
from app.telegram_bot.command_bot import TelegramCommandBot


class FakeService:
    def __init__(self) -> None:
        self.paused = False
        self.notifier = None

    def status_text(self) -> str:
        return "CryptoRadar Status\nScanner: running"


class FakeResolver:
    @staticmethod
    def resolve_symbol(value: str) -> str:
        cleaned = value.upper()
        return cleaned if cleaned.endswith("USDT") else f"{cleaned}USDT"


class FakeNews:
    def __init__(self) -> None:
        self.checked: list[str] = []

    def check_coin_news(self, symbol: str):
        self.checked.append(symbol)
        return [{"sent": True}]

    @staticmethod
    def format_coin_news_summary(symbol: str) -> str:
        return f"News summary for {symbol}"


def test_prefer_and_unprefer_commands(config: dict, db) -> None:
    bot = TelegramCommandBot(config, db, FakeService())
    bot.coin_alerts = FakeResolver()

    response = bot.handle_command("/prefer SOL BTCUSDT PEPE")

    assert "SOLUSDT" in response
    rows = UserListStore(db).preferred()
    assert sorted(row["symbol"] for row in rows) == ["BTCUSDT", "PEPEUSDT", "SOLUSDT"]

    response = bot.handle_command("/unprefer SOL")
    assert "SOLUSDT" in response
    assert sorted(row["symbol"] for row in UserListStore(db).preferred()) == ["BTCUSDT", "PEPEUSDT"]


def test_watch_list_remove_and_pause_resume(config: dict, db) -> None:
    service = FakeService()
    bot = TelegramCommandBot(config, db, service)
    bot.coin_alerts = FakeResolver()

    assert "Holding added" in bot.handle_command("/watch SOL 100 2.5")
    assert "SOLUSDT" in bot.handle_command("/list")
    assert "Holding removed" in bot.handle_command("/remove SOL")
    assert "No holdings" in bot.handle_command("/list")

    assert "paused" in bot.handle_command("/pause").lower()
    assert service.paused is True
    assert "resumed" in bot.handle_command("/resume").lower()
    assert service.paused is False


def test_status_mlstatus_and_help(config: dict, db) -> None:
    bot = TelegramCommandBot(config, db, FakeService())
    assert "CryptoRadar Status" in bot.handle_command("/status")
    assert "ML Status" in bot.handle_command("/mlstatus")
    assert "/prefer" in bot.handle_command("/help")


def test_prefer_triggers_news_check_when_enabled(config: dict, db) -> None:
    config["news"]["enabled"] = True
    bot = TelegramCommandBot(config, db, FakeService())
    bot.coin_alerts = FakeResolver()
    bot.news = FakeNews()

    response = bot.handle_command("/prefer FOREST")

    assert "FORESTUSDT" in response
    assert "News alerts checked. Sent: 1." in response
    assert bot.news.checked == ["FORESTUSDT"]


def test_news_command_returns_summary(config: dict, db) -> None:
    config["news"]["enabled"] = True
    bot = TelegramCommandBot(config, db, FakeService())
    bot.news = FakeNews()

    assert bot.handle_command("/news FOREST") == "News summary for FOREST"
