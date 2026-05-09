from __future__ import annotations

from typing import Any


class SignalPerformanceService:
    def __init__(self, db: Any):
        self.db = db

    def update_future_price(self, signal_id: str, horizon: str, price: float) -> None:
        allowed = {"15m": "price_15m", "1h": "price_1h", "4h": "price_4h", "24h": "price_24h", "7d": "price_7d"}
        column = allowed[horizon]
        self.db.execute(
            f"""
            INSERT INTO signal_performance(signal_id, {column}, final_result, updated_at)
            VALUES (?, ?, 'unknown', CURRENT_TIMESTAMP)
            ON CONFLICT(signal_id) DO UPDATE SET {column}=excluded.{column}, updated_at=CURRENT_TIMESTAMP
            """,
            (signal_id, price),
        )

    def classify_buy_result(self, signal_id: str) -> str:
        signal = self.db.query_one("SELECT price FROM signals WHERE id=?", (signal_id,))
        perf = self.db.query_one("SELECT * FROM signal_performance WHERE signal_id=?", (signal_id,))
        if not signal or not perf or perf.get("price_24h") is None:
            return "unknown"
        entry = float(signal["price"])
        move = (float(perf["price_24h"]) - entry) / entry * 100
        if move >= 3:
            result = "win"
        elif move <= -2:
            result = "loss"
        else:
            result = "neutral"
        self.db.execute("UPDATE signal_performance SET final_result=? WHERE signal_id=?", (result, signal_id))
        self.db.execute("UPDATE signals SET final_result=? WHERE id=?", (result, signal_id))
        return result
