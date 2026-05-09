from __future__ import annotations

from typing import Any


class LearningStore:
    def __init__(self, db: Any):
        self.db = db

    def set_weight(self, key: str, value: float, min_value: float = -20, max_value: float = 20) -> None:
        self.db.execute(
            """
            INSERT INTO adaptive_weights(key, value, min_value, max_value, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
            """,
            (key, value, min_value, max_value),
        )

    def weights(self) -> dict[str, float]:
        return {row["key"]: float(row["value"]) for row in self.db.query("SELECT key, value FROM adaptive_weights")}
