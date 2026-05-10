from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.alerts.coin_alerts import CoinAlertService, format_price, format_pct
from app.notifications.notification_service import NotificationService
from app.storage.user_lists import UserListStore


class HoldingsMonitor:
    def __init__(self, config: dict[str, Any], db: Any, coin_alerts: CoinAlertService, notifier: NotificationService):
        self.config = config
        self.db = db
        self.store = UserListStore(db)
        self.coin_alerts = coin_alerts
        self.notifier = notifier

    def check_holdings(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for holding in self.store.holdings():
            result = self.check_holding(holding)
            results.append(result)
        return results

    def check_holding(self, holding: dict[str, Any]) -> dict[str, Any]:
        symbol = holding["symbol"]
        try:
            market = self.coin_alerts.resolve_market(symbol)
            alert = self.coin_alerts.build_alert(market)
        except Exception as exc:
            return {"symbol": symbol, "sent": False, "error": type(exc).__name__}
        entry = float(holding.get("entry_price") or 0)
        price = float(alert.get("price") or 0)
        move_pct = ((price - entry) / entry * 100) if entry else 0.0
        triggers = holding_triggers(move_pct, alert)
        if not triggers or self._in_cooldown(holding):
            return {"symbol": symbol, "sent": False, "move_pct": move_pct, "triggers": triggers}
        message = format_holding_alert(symbol, entry, price, move_pct, triggers, alert)
        sent = self.notifier.send_text(message, signal={"id": f"holding-{symbol}", "symbol": symbol})
        if sent:
            self.store.touch_holding_alert(symbol)
        return {"symbol": symbol, "sent": sent, "move_pct": move_pct, "triggers": triggers}

    def _in_cooldown(self, holding: dict[str, Any]) -> bool:
        raw = holding.get("last_alert_time")
        if not raw:
            return False
        cooldown = int(self.config.get("coin_alerts", {}).get("preferred_cooldown_minutes", 15))
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last < timedelta(minutes=cooldown)


def holding_triggers(move_pct: float, alert: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    if move_pct >= 8:
        triggers.append("profit zone reached")
    if move_pct <= -4:
        triggers.append("risk zone reached")
    event_types = {event.get("type") for event in alert.get("events", [])}
    if event_types.intersection({"DUMP", "FAST_MOVE_DOWN", "HIGH_RISK_PUMP"}):
        triggers.append("urgent market movement")
    if event_types.intersection({"SURGE", "FAST_MOVE_UP", "VOLUME_SPIKE"}):
        triggers.append("strong movement on holding")
    return list(dict.fromkeys(triggers))


def format_holding_alert(symbol: str, entry: float, price: float, move_pct: float, triggers: list[str], alert: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"P1 HOLDING ALERT - {alert.get('display_symbol') or symbol}",
            f"Entry: {format_price(entry)}",
            f"Current: {format_price(price)}",
            f"Move from entry: {format_pct(move_pct)}",
            f"24h Change: {format_pct(alert.get('change_24h'))}",
            "",
            "Why this matters:",
            *[f"- {trigger}" for trigger in triggers],
            "",
            "Risk note:",
            "Review manually. CryptoRadar does not sell, buy, or execute orders.",
            "",
            "Final:",
            "This is an analysis-based holding alert, not guaranteed profit. Decide manually.",
        ]
    )
