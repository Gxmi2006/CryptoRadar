from __future__ import annotations

from typing import Any


class UserListStore:
    def __init__(self, db: Any):
        self.db = db

    def add_preferred(
        self,
        symbol: str,
        category: str = "preferred",
        sensitivity: str = "high",
        cooldown_minutes: int = 15,
        notes: str = "",
    ) -> None:
        self.db.execute(
            """
            INSERT INTO preferred_coins(symbol, category, alert_sensitivity, cooldown_minutes, notes, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(symbol) DO UPDATE SET
                category=excluded.category,
                alert_sensitivity=excluded.alert_sensitivity,
                cooldown_minutes=excluded.cooldown_minutes,
                notes=excluded.notes,
                active=1
            """,
            (symbol.upper(), category, sensitivity, cooldown_minutes, notes),
        )

    def remove_preferred(self, symbol: str) -> None:
        self.db.execute("UPDATE preferred_coins SET active=0 WHERE symbol=?", (symbol.upper(),))

    def clear_preferred(self) -> None:
        self.db.execute("UPDATE preferred_coins SET active=0")

    def preferred(self) -> list[dict[str, Any]]:
        return self.db.query(
            """
            SELECT * FROM preferred_coins
            WHERE active=1
            ORDER BY datetime(added_time) ASC, symbol ASC
            """
        )

    def add_holding(self, symbol: str, entry_price: float, amount: float = 0, category: str = "holding") -> None:
        self.db.execute(
            """
            INSERT INTO holdings(symbol, entry_price, amount, category, alert_settings, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(symbol) DO UPDATE SET
                entry_price=excluded.entry_price,
                amount=excluded.amount,
                category=excluded.category,
                active=1
            """,
            (symbol.upper(), float(entry_price), float(amount or 0), category, "{}"),
        )

    def remove_holding(self, symbol: str) -> None:
        self.db.execute("UPDATE holdings SET active=0 WHERE symbol=?", (symbol.upper(),))

    def holdings(self) -> list[dict[str, Any]]:
        return self.db.query(
            """
            SELECT * FROM holdings
            WHERE active=1
            ORDER BY datetime(added_time) ASC, symbol ASC
            """
        )

    def touch_holding_alert(self, symbol: str) -> None:
        self.db.execute("UPDATE holdings SET last_alert_time=CURRENT_TIMESTAMP WHERE symbol=?", (symbol.upper(),))
