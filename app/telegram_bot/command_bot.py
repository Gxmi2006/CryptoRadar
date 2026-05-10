from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.alerts.coin_alerts import CoinAlertService
from app.learning.ml_model import FutureMLModel
from app.news.preferred_news import PreferredNewsService
from app.notifications.telegram import TelegramNotifier
from app.storage.user_lists import UserListStore


log = logging.getLogger(__name__)


class TelegramCommandBot:
    def __init__(self, config: dict[str, Any], db: Any, service: Any):
        self.config = config
        self.db = db
        self.service = service
        self.telegram = TelegramNotifier(config)
        self.store = UserListStore(db)
        self.coin_alerts = CoinAlertService(config, db, notifier=service.notifier)
        self.news = PreferredNewsService(config, db, self.coin_alerts, self.coin_alerts.notifier)
        self.offset: int | None = None
        self.running = False

    async def run_forever(self, status=None) -> None:
        self.running = True
        if not self.telegram.token:
            if status:
                status("Telegram bot listener: not configured")
            while True:
                await asyncio.sleep(60)
        if status:
            status("Telegram bot listener: running" if self.telegram.token else "Telegram bot listener: not configured")
        while True:
            try:
                updates = await asyncio.to_thread(self.telegram.get_updates, self.offset, 25)
                for update in updates:
                    self.offset = int(update.get("update_id", 0)) + 1
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Telegram command listener failed: %s", exc)
                if status:
                    status("Telegram connection issue. Retrying...")
                await asyncio.sleep(10)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = str(message.get("text") or "").strip()
        chat_id = str((message.get("chat") or {}).get("id") or "")
        if not text.startswith("/"):
            return
        if self.telegram.chat_id and chat_id != str(self.telegram.chat_id):
            log.info("Ignoring Telegram command from unconfigured chat id")
            return
        response = self.handle_command(text)
        self.telegram.send(response)

    def handle_command(self, text: str) -> str:
        parts = text.strip().split()
        command = parts[0].split("@", 1)[0].lower()
        args = parts[1:]
        try:
            if command == "/status":
                return self.service.status_text()
            if command == "/mlstatus":
                return ml_status_text(self.config, self.db, self.service)
            if command == "/prefer":
                return self._prefer(args)
            if command == "/unprefer":
                return self._unprefer(args)
            if command == "/preferred":
                return self._preferred()
            if command == "/clearpreferred":
                self.store.clear_preferred()
                return "Preferred coin list cleared."
            if command == "/news":
                return self._news(args)
            if command == "/watch":
                return self._watch(args)
            if command == "/list":
                return self._list_holdings()
            if command == "/remove":
                return self._remove(args)
            if command == "/pause":
                self.service.paused = True
                return "CryptoRadar paused. Telegram commands still work; no trading actions exist."
            if command == "/resume":
                self.service.paused = False
                return "CryptoRadar resumed. Scanner and monitors will continue."
            if command == "/help":
                return help_text()
        except Exception as exc:
            log.warning("Telegram command failed: %s", exc)
            return f"Command failed: {type(exc).__name__}. Check spelling and try /help."
        return "Unknown command. Try /help."

    def _prefer(self, args: list[str]) -> str:
        if not args:
            return "Usage: /prefer SOLUSDT BTCUSDT PEPEUSDT"
        added: list[str] = []
        news_sent = 0
        cooldown = int(self.config.get("coin_alerts", {}).get("preferred_cooldown_minutes", 15))
        for raw in args:
            symbol = self.coin_alerts.resolve_symbol(raw)
            self.store.add_preferred(symbol, cooldown_minutes=cooldown)
            added.append(symbol)
            if self.config.get("news", {}).get("enabled", True):
                try:
                    news_sent += sum(1 for alert in self.news.check_coin_news(symbol) if alert.get("sent"))
                except Exception as exc:
                    log.warning("Immediate preferred news check failed for %s: %s", symbol, type(exc).__name__)
        response = "Preferred coins added:\n" + "\n".join(f"- {symbol}" for symbol in added)
        if self.config.get("news", {}).get("enabled", True):
            response += f"\nNews alerts checked. Sent: {news_sent}."
        return response

    def _unprefer(self, args: list[str]) -> str:
        if not args:
            return "Usage: /unprefer SOLUSDT"
        removed: list[str] = []
        for raw in args:
            symbol = self.coin_alerts.resolve_symbol(raw)
            self.store.remove_preferred(symbol)
            removed.append(symbol)
        return "Preferred coins removed:\n" + "\n".join(f"- {symbol}" for symbol in removed)

    def _preferred(self) -> str:
        rows = self.store.preferred()
        if not rows:
            return "No preferred coins yet. Add one with /prefer SOLUSDT"
        return "Preferred coins:\n" + "\n".join(f"- {row['symbol']} sensitivity={row['alert_sensitivity']}" for row in rows)

    def _news(self, args: list[str]) -> str:
        if not args:
            return "Usage: /news SOLUSDT"
        return self.news.format_coin_news_summary(args[0])

    def _watch(self, args: list[str]) -> str:
        if len(args) < 2:
            return "Usage: /watch SOLUSDT ENTRY_PRICE [AMOUNT]"
        symbol = self.coin_alerts.resolve_symbol(args[0])
        entry = float(args[1])
        amount = float(args[2]) if len(args) >= 3 else 0.0
        self.store.add_holding(symbol, entry, amount)
        return f"Holding added: {symbol} entry={entry:g} amount={amount:g}. Alerts are notification-only."

    def _remove(self, args: list[str]) -> str:
        if not args:
            return "Usage: /remove SOLUSDT"
        symbol = self.coin_alerts.resolve_symbol(args[0])
        self.store.remove_holding(symbol)
        return f"Holding removed: {symbol}"

    def _list_holdings(self) -> str:
        rows = self.store.holdings()
        if not rows:
            return "No holdings tracked yet. Add one with /watch SOLUSDT ENTRY_PRICE [AMOUNT]"
        return "Tracked holdings:\n" + "\n".join(
            f"- {row['symbol']} entry={float(row['entry_price'] or 0):g} amount={float(row['amount'] or 0):g}" for row in rows
        )


def ml_status_text(config: dict[str, Any], db: Any, service: Any | None = None) -> str:
    report = FutureMLModel(db, config).report()
    lines = report.splitlines()
    learning = "running" if service is None or not getattr(service, "paused", False) else "paused"
    return "\n".join(["ML Status", *lines[1:], f"Learning: {learning}"])


def help_text() -> str:
    return "\n".join(
        [
            "CryptoRadar commands:",
            "/status - service health",
            "/mlstatus - ML learner status",
            "/prefer SOLUSDT BTCUSDT - add preferred coins",
            "/unprefer SOLUSDT - remove preferred coin",
            "/preferred - list preferred coins",
            "/clearpreferred - clear preferred list",
            "/news SOLUSDT - latest important news and ML breakout status",
            "/watch SOLUSDT ENTRY [AMOUNT] - track a holding",
            "/list - list holdings",
            "/remove SOLUSDT - remove holding",
            "/pause - pause scanner loops",
            "/resume - resume scanner loops",
            "/help - show this help",
            "CryptoRadar is notification-only and cannot trade.",
        ]
    )
