from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any

from app.ai.telegram_message_formatter import TelegramMessageFormatter
from app.notifications.desktop import DesktopNotifier
from app.notifications.discord import DiscordNotifier
from app.notifications.email_notifier import EmailNotifier
from app.notifications.telegram import TelegramNotifier


log = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, config: dict[str, Any], db: Any):
        self.config = config
        self.db = db
        self.telegram = TelegramNotifier(config)
        self.desktop = DesktopNotifier()
        self.email = EmailNotifier(config)
        self.discord = DiscordNotifier(config)
        self.telegram_formatter = TelegramMessageFormatter(config)

    def notify_signal(self, signal: dict[str, Any]) -> bool:
        if not self.should_notify(signal):
            return False
        message = self._format_notification(signal)
        return self.send_text(message, signal=signal)

    def send_text(self, message: str, signal: dict[str, Any] | None = None) -> bool:
        sent = False
        if self.config["notifications"].get("telegram_enabled", True):
            telegram_sent = self.telegram.send(message)
            if telegram_sent:
                log.info("Telegram message sent")
            sent = telegram_sent or sent
            self._log(signal, "telegram", "sent" if telegram_sent else "skipped_or_failed", message)
        if self.config["notifications"].get("desktop_enabled", False):
            sent = self.desktop.send("CryptoRadar", message[:240]) or sent
            self._log(signal, "desktop", "sent", message)
        if self.config["notifications"].get("email_enabled", False):
            sent = self.email.send("CryptoRadar Alert", message) or sent
            self._log(signal, "email", "sent", message)
        if self.config["notifications"].get("discord_enabled", False):
            sent = self.discord.send(message) or sent
            self._log(signal, "discord", "sent", message)
        return sent

    def send_test(self) -> bool:
        return self.send_text("CryptoRadar Telegram test. Notifications only; no trading actions are available.")

    def send_daily_summary(self, summary: str) -> bool:
        return self.send_text(summary)

    def should_notify(self, signal: dict[str, Any]) -> bool:
        if self._quiet_hours_now():
            return False
        signal_type = self._signal_type(signal)
        score = int(signal["score"])
        scanner = self.config["scanner"]
        notifications = self.config.get("notifications", {})
        notify_key = f"notify_{signal_type.lower()}"
        default_enabled = signal_type in {"BUY", "SELL", "HIGH_RISK"}
        if not notifications.get(notify_key, default_enabled):
            return False
        if signal_type == "BUY" and score < int(scanner.get("buy_score_threshold", 70)):
            return False
        if signal_type == "SELL" and score < int(scanner.get("sell_score_threshold", 70)):
            return False
        if signal_type == "HIGH_RISK" and score < int(scanner.get("high_risk_threshold", 65)):
            return False
        if not self._under_hourly_limit():
            return False
        if self._in_cooldown(signal):
            return False
        return True

    def format_signal(self, signal: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"{self._signal_type(signal)} SIGNAL: {signal['symbol']}",
                f"Score: {signal['score']}/100",
                f"Confidence: {signal['confidence']}",
                f"Risk: {signal['risk_level']}",
                "",
                "Reason:",
                signal["main_reason"],
                "",
                "Entry Zone:",
                str(signal.get("possible_entry_zone", "Review manually")),
                "",
                "Invalidation:",
                str(signal.get("invalidation_level", "Review manually")),
                "",
                "Learning Note:",
                "Adaptive scoring will include this signal after outcome tracking.",
                "",
                "Warning:",
                signal.get("warning", "Do not chase if price moves too far."),
                "",
                "This is not guaranteed profit. Decide manually.",
            ]
        )

    def _format_notification(self, signal: dict[str, Any]) -> str:
        if self.config.get("telegram_formatting", {}).get("use_template_formatter", True):
            return self.telegram_formatter.format(signal)
        return self.format_signal(signal)

    def _in_cooldown(self, signal: dict[str, Any]) -> bool:
        cooldown = int(self.config["scanner"].get("cooldown_minutes", 30))
        rows = self.db.query(
            """
            SELECT created_at FROM notifications
            WHERE symbol=? AND status='sent'
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (signal["symbol"],),
        )
        if not rows:
            return False
        last = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last < timedelta(minutes=cooldown)

    def _under_hourly_limit(self) -> bool:
        limit = int(self.config["notifications"].get("max_alerts_per_hour", 10))
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE datetime(created_at) >= datetime('now', '-1 hour') AND status='sent'"
        )
        return int(row["count"]) < limit if row else True

    def _quiet_hours_now(self) -> bool:
        cfg = self.config["notifications"].get("quiet_hours", {})
        if not cfg.get("enabled"):
            return False
        start = _parse_time(cfg.get("start", "22:00"))
        end = _parse_time(cfg.get("end", "07:00"))
        now = datetime.now().time()
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end

    def _log(self, signal: dict[str, Any] | None, channel: str, status: str, message: str) -> None:
        self.db.execute(
            "INSERT INTO notifications(signal_id, symbol, channel, status, message) VALUES (?, ?, ?, ?, ?)",
            (
                signal.get("id") if signal else None,
                signal.get("symbol") if signal else None,
                channel,
                status,
                message[:4000],
            ),
        )

    @staticmethod
    def _signal_type(signal: dict[str, Any]) -> str:
        return str(signal.get("signal_type") or signal.get("type") or "").upper()


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":", 1)
    return time(int(hours), int(minutes))
