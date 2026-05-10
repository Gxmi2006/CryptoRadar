from __future__ import annotations

from typing import Any


class SignalStore:
    def __init__(self, db: Any):
        self.db = db

    def save(self, signal: dict[str, Any]) -> None:
        self.db.execute(
            """
            INSERT INTO signals(
                id, symbol, signal_type, created_at, price, score, confidence,
                risk_level, timeframe, main_reason, payload_json, final_result
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown')
            ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (
                signal["id"],
                signal["symbol"],
                signal["signal_type"],
                signal["created_at"],
                signal["price"],
                signal["score"],
                signal["confidence"],
                signal["risk_level"],
                signal["timeframe"],
                signal["main_reason"],
                self.db.dumps(signal),
            ),
        )
        scores = signal.get("score_details", {})
        self.db.execute(
            """
            INSERT INTO signal_scores(
                signal_id, buy_score, sell_score, hold_score, wait_score,
                avoid_score, high_risk_score, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal["id"],
                scores.get("buy_score", 0),
                scores.get("sell_score", 0),
                scores.get("hold_score", 0),
                scores.get("wait_score", 0),
                scores.get("avoid_score", 0),
                scores.get("high_risk_score", 0),
                self.db.dumps(scores),
            ),
        )
        self.db.execute(
            "INSERT INTO ai_analysis(signal_id, provider, model, analysis_text) VALUES (?, ?, ?, ?)",
            (
                signal["id"],
                "ollama_or_fallback",
                "configured-local-model",
                signal.get("ai_analysis", ""),
            ),
        )
        prediction = signal.get("ml_prediction")
        if prediction:
            self.db.execute(
                """
                INSERT INTO ml_predictions(
                    signal_id, symbol, success_probability, risk_score,
                    confidence_score, data_quality, model_version, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["id"],
                    signal["symbol"],
                    prediction.get("success_probability"),
                    prediction.get("risk_score"),
                    prediction.get("confidence_score"),
                    prediction.get("data_quality"),
                    prediction.get("model_version"),
                    self.db.dumps(prediction),
                ),
            )
        for source in signal.get("knowledge_sources_used", []):
            self.db.execute(
                "INSERT INTO citations(signal_id, source_id, file_name, chunk_id, quote) VALUES (?, ?, ?, ?, ?)",
                (signal["id"], "", source, "", ""),
            )
