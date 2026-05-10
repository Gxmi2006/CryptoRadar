from __future__ import annotations

from typing import Any, Iterable


class CollectorStore:
    def __init__(self, db: Any):
        self.db = db

    def save_snapshots(self, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        self.db.executemany(
            """
            INSERT INTO broad_market_snapshots(
                symbol, base_asset, quote_asset, price, change_1h, change_4h,
                change_24h, volume_usdt, high_24h, low_24h, data_quality,
                quality_reasons_json, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["symbol"],
                    row.get("base_asset"),
                    row.get("quote_asset"),
                    row.get("price", 0),
                    row.get("change_1h", 0),
                    row.get("change_4h", 0),
                    row.get("change_24h", 0),
                    row.get("volume_usdt", 0),
                    row.get("high_24h", 0),
                    row.get("low_24h", 0),
                    row.get("data_quality", "thin"),
                    self.db.dumps(row.get("quality_reasons", [])),
                    self.db.dumps(row.get("payload", row)),
                )
                for row in rows
            ),
        )
        self.db.executemany(
            """
            INSERT INTO symbol_data_quality(
                symbol, data_quality, quality_reasons_json, volume_usdt, candle_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                data_quality=excluded.data_quality,
                quality_reasons_json=excluded.quality_reasons_json,
                volume_usdt=excluded.volume_usdt,
                candle_count=excluded.candle_count,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                (
                    row["symbol"],
                    row.get("data_quality", "thin"),
                    self.db.dumps(row.get("quality_reasons", [])),
                    row.get("volume_usdt", 0),
                    row.get("candle_count", 0),
                )
                for row in rows
            ),
        )
        candle_rows = []
        for row in rows:
            symbol = row["symbol"]
            interval = row.get("candle_interval")
            if not interval:
                continue
            for candle in row.get("candles", []) or []:
                candle_rows.append(
                    (
                        symbol,
                        interval,
                        int(candle["open_time"]),
                        candle.get("open", 0),
                        candle.get("high", 0),
                        candle.get("low", 0),
                        candle.get("close", 0),
                        candle.get("volume", 0),
                        int(candle.get("close_time", candle["open_time"])),
                    )
                )
        if candle_rows:
            self.db.executemany(
                """
                INSERT INTO candles(symbol, interval, open_time, open, high, low, close, volume, close_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    close_time=excluded.close_time
                """,
                candle_rows,
            )

    def latest_quality(self, symbol: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM symbol_data_quality WHERE symbol=?", (symbol,))

    def coverage_stats(self) -> dict[str, Any]:
        total_snapshots = self.db.query_one("SELECT COUNT(*) AS count FROM broad_market_snapshots")
        total_symbols = self.db.query_one("SELECT COUNT(*) AS count FROM symbol_data_quality")
        quality_counts = self.db.query(
            """
            SELECT data_quality, COUNT(*) AS count
            FROM symbol_data_quality
            GROUP BY data_quality
            ORDER BY count DESC
            """
        )
        lowest_volume = self.db.query(
            """
            SELECT symbol, data_quality, volume_usdt
            FROM symbol_data_quality
            ORDER BY volume_usdt ASC
            LIMIT 10
            """
        )
        weak_symbols = self.db.query(
            """
            SELECT symbol, data_quality
            FROM symbol_data_quality
            WHERE data_quality IN ('thin', 'low_volume', 'missing_candles')
            ORDER BY updated_at DESC
            LIMIT 20
            """
        )
        return {
            "total_snapshots": int(total_snapshots["count"]) if total_snapshots else 0,
            "total_symbols": int(total_symbols["count"]) if total_symbols else 0,
            "quality_counts": quality_counts,
            "lowest_volume": lowest_volume,
            "weak_symbols": weak_symbols,
        }
