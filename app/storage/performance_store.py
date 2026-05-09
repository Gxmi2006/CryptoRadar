from __future__ import annotations

from typing import Any


class PerformanceStore:
    def __init__(self, db: Any):
        self.db = db

    def recent_results(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.db.query(
            """
            SELECT s.*, p.*
            FROM signals s
            LEFT JOIN signal_performance p ON p.signal_id = s.id
            ORDER BY datetime(s.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
