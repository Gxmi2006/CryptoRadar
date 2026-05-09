from __future__ import annotations

from typing import Any


class FeedbackService:
    def __init__(self, db: Any):
        self.db = db

    def mark(self, signal_id: str, result: str, notes: str = "") -> None:
        if result not in {"win", "loss", "neutral"}:
            raise ValueError("result must be win, loss, or neutral")
        self.db.execute(
            "INSERT INTO manual_feedback(signal_id, result, notes) VALUES (?, ?, ?)",
            (signal_id, result, notes),
        )
        self.db.execute("UPDATE signals SET final_result=? WHERE id=?", (result, signal_id))
        self.db.execute(
            """
            INSERT INTO signal_performance(signal_id, final_result, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(signal_id) DO UPDATE SET final_result=excluded.final_result, updated_at=CURRENT_TIMESTAMP
            """,
            (signal_id, result),
        )
