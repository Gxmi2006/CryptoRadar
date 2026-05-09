from __future__ import annotations

from app.learning.adaptive_scoring import AdaptiveScoringEngine


def test_adaptive_scoring_waits_for_minimum_samples(config: dict, db) -> None:
    config["learning"]["min_samples_before_weight_change"] = 30
    suggestions = AdaptiveScoringEngine(db, config).suggested_changes()
    assert suggestions[0].startswith("Need at least 30")


def test_adaptive_scoring_suggests_slow_buy_increase(config: dict, db) -> None:
    for index in range(30):
        db.execute(
            """
            INSERT INTO signals(id, symbol, signal_type, created_at, price, score, confidence, risk_level, timeframe, main_reason, payload_json, final_result)
            VALUES (?, 'SOLUSDT', 'BUY', CURRENT_TIMESTAMP, 100, 75, 'Medium', 'Medium', '15m', 'test', '{}', 'win')
            """,
            (f"sig-{index}",),
        )
    suggestions = AdaptiveScoringEngine(db, config).suggested_changes()
    assert any("increase BUY" in item for item in suggestions)
