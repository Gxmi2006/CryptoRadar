from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class PaperTradeTracker:
    def __init__(self, db: Any, config: dict[str, Any]):
        self.db = db
        self.config = config

    def create_for_signal(self, signal: dict[str, Any]) -> str:
        trade_id = f"paper-{uuid4().hex[:12]}"
        side = signal["signal_type"]
        entry = self._entry_price(signal)
        stop = float(signal.get("possible_stop_loss_zone") or signal.get("invalidation_level") or signal["price"] * 0.97)
        take_profit = self._first_take_profit(signal) or signal["price"] * 1.04
        status = "waiting_entry" if side == "BUY" else "tracking"
        self.db.execute(
            """
            INSERT INTO paper_trades(
                id, signal_id, symbol, side, status, entry_price, current_price,
                take_profit, stop_loss, invalidation, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                signal["id"],
                signal["symbol"],
                side,
                status,
                entry,
                signal["price"],
                take_profit,
                stop,
                float(signal.get("invalidation_level") or stop),
                self.db.dumps(signal),
            ),
        )
        return trade_id

    def refresh_open_trades(self, snapshots: dict[str, dict[str, Any]]) -> None:
        rows = self.db.query("SELECT * FROM paper_trades WHERE result='unknown'")
        for row in rows:
            snapshot = snapshots.get(row["symbol"])
            if not snapshot:
                continue
            self.update_with_price(row["id"], float(snapshot["price"]))

    def update_with_price(self, trade_id: str, price: float) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM paper_trades WHERE id=?", (trade_id,))
        if not row:
            return None
        entry = float(row["entry_price"] or row["current_price"] or price)
        status = row["status"]
        result = row["result"]
        if status == "waiting_entry":
            status = "open"
            entry = price

        move_pct = self._move_pct(row["side"], entry, price)
        max_profit = max(float(row["max_profit_pct"] or 0), move_pct)
        max_drawdown = min(float(row["max_drawdown_pct"] or 0), move_pct)
        if row["side"] == "BUY":
            if price >= float(row["take_profit"] or 0):
                result = "win"
                status = "closed"
            elif price <= float(row["stop_loss"] or 0):
                result = "loss"
                status = "closed"
        elif row["side"] in {"SELL", "HIGH_RISK"}:
            if move_pct >= 3:
                result = "win"
            elif move_pct <= -3:
                result = "loss"
        elif abs(move_pct) < 2:
            result = "neutral"

        self.db.execute(
            """
            UPDATE paper_trades
            SET status=?, entry_price=?, current_price=?, max_profit_pct=?,
                max_drawdown_pct=?, result=?, updated_at=?
            WHERE id=?
            """,
            (status, entry, price, max_profit, max_drawdown, result, datetime.now(timezone.utc).isoformat(), trade_id),
        )
        if result in {"win", "loss", "neutral"}:
            self.db.execute(
                """
                INSERT INTO signal_performance(signal_id, max_profit_pct, max_drawdown_pct, final_result, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(signal_id) DO UPDATE SET
                    max_profit_pct=excluded.max_profit_pct,
                    max_drawdown_pct=excluded.max_drawdown_pct,
                    final_result=excluded.final_result,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (row["signal_id"], max_profit, max_drawdown, result),
            )
            self.db.execute("UPDATE signals SET final_result=? WHERE id=?", (result, row["signal_id"]))
        return self.db.query_one("SELECT * FROM paper_trades WHERE id=?", (trade_id,))

    @staticmethod
    def _move_pct(side: str, entry: float, price: float) -> float:
        if not entry:
            return 0.0
        raw = (price - entry) / entry * 100
        if side in {"SELL", "HIGH_RISK"}:
            return -raw
        return raw

    @staticmethod
    def _entry_price(signal: dict[str, Any]) -> float:
        zone = str(signal.get("possible_entry_zone") or "")
        if "-" in zone:
            try:
                low, high = [float(part) for part in zone.split("-", 1)]
                return (low + high) / 2
            except ValueError:
                pass
        return float(signal["price"])

    @staticmethod
    def _first_take_profit(signal: dict[str, Any]) -> float | None:
        zones = signal.get("possible_take_profit_zones") or []
        if isinstance(zones, list) and zones:
            return float(zones[0])
        return None
