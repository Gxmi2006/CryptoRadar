from __future__ import annotations

from typing import Any, Iterable


class MarketStore:
    def __init__(self, db: Any):
        self.db = db

    def save_snapshots(self, snapshots: Iterable[dict[str, Any]]) -> None:
        self.db.executemany(
            """
            INSERT INTO market_snapshots(symbol, price, change_1h, change_4h, change_24h, volume_usdt, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    item.get("symbol"),
                    item.get("price"),
                    item.get("change_1h", 0),
                    item.get("change_4h", 0),
                    item.get("change_24h", 0),
                    item.get("volume_usdt", 0),
                    self.db.dumps(item.get("payload", item)),
                )
                for item in snapshots
            ),
        )
