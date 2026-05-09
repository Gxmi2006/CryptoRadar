from __future__ import annotations

from typing import Any


class AdaptiveScoringEngine:
    def __init__(self, db: Any, config: dict[str, Any]):
        self.db = db
        self.config = config

    def load_weights(self) -> dict[str, float]:
        rows = self.db.query("SELECT key, value FROM adaptive_weights")
        if not rows:
            self._seed()
            rows = self.db.query("SELECT key, value FROM adaptive_weights")
        return {row["key"]: float(row["value"]) for row in rows}

    def _seed(self) -> None:
        for key in ("buy_bias", "sell_bias", "volume_breakout_bias", "btc_bear_penalty"):
            self.db.execute(
                "INSERT OR IGNORE INTO adaptive_weights(key, value, min_value, max_value) VALUES (?, 0, -20, 20)",
                (key,),
            )

    def suggested_changes(self) -> list[str]:
        min_samples = int(self.config["learning"].get("min_samples_before_weight_change", 30))
        rows = self.db.query(
            """
            SELECT s.signal_type, s.symbol, s.timeframe, s.final_result, ss.details_json
            FROM signals s
            LEFT JOIN signal_scores ss ON ss.signal_id = s.id
            WHERE s.final_result IN ('win', 'loss', 'neutral')
            """
        )
        if len(rows) < min_samples:
            return [f"Need at least {min_samples} completed signals before changing weights. Current completed sample size: {len(rows)}."]
        buy_rows = [row for row in rows if row["signal_type"] == "BUY"]
        sell_rows = [row for row in rows if row["signal_type"] == "SELL"]
        suggestions: list[str] = []
        suggestions.extend(self._win_rate_suggestion("BUY", buy_rows))
        suggestions.extend(self._win_rate_suggestion("SELL", sell_rows))
        return suggestions or ["No scoring weight changes suggested yet."]

    def maybe_update_weights(self) -> list[str]:
        if not self.config["learning"].get("auto_adjust_weights", True):
            return ["Automatic weight updates are disabled."]
        suggestions = self.suggested_changes()
        if suggestions and suggestions[0].startswith("Need at least"):
            return suggestions
        strength = float(self.config["learning"].get("weight_update_strength", 0.05))
        for suggestion in suggestions:
            if "increase BUY" in suggestion:
                self._nudge("buy_bias", strength)
            if "reduce BUY" in suggestion:
                self._nudge("buy_bias", -strength)
            if "increase SELL" in suggestion:
                self._nudge("sell_bias", strength)
            if "reduce SELL" in suggestion:
                self._nudge("sell_bias", -strength)
        return suggestions

    def _nudge(self, key: str, delta: float) -> None:
        row = self.db.query_one("SELECT value, min_value, max_value FROM adaptive_weights WHERE key=?", (key,))
        if not row:
            self._seed()
            row = self.db.query_one("SELECT value, min_value, max_value FROM adaptive_weights WHERE key=?", (key,))
        value = max(float(row["min_value"]), min(float(row["max_value"]), float(row["value"]) + delta))
        self.db.execute("UPDATE adaptive_weights SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?", (value, key))

    @staticmethod
    def _win_rate_suggestion(label: str, rows: list[dict[str, Any]]) -> list[str]:
        if len(rows) < 30:
            return []
        wins = sum(1 for row in rows if row["final_result"] == "win")
        rate = wins / len(rows)
        if rate >= 0.62:
            return [f"Historical {label} win rate is {rate:.0%}; increase {label} influence slowly."]
        if rate <= 0.42:
            return [f"Historical {label} win rate is {rate:.0%}; reduce {label} influence slowly."]
        return [f"Historical {label} win rate is {rate:.0%}; keep {label} influence stable."]
