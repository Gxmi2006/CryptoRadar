from __future__ import annotations

from app.learning.feedback import FeedbackService
from app.learning.signal_performance import SignalPerformanceService


def insert_signal(db, signal_id: str = "sig-perf") -> None:
    db.execute(
        """
        INSERT INTO signals(id, symbol, signal_type, created_at, price, score, confidence, risk_level, timeframe, main_reason, payload_json)
        VALUES (?, 'SOLUSDT', 'BUY', CURRENT_TIMESTAMP, 100, 75, 'Medium', 'Medium', '15m', 'test', '{}')
        """,
        (signal_id,),
    )


def test_signal_performance_classifies_buy_result(db) -> None:
    insert_signal(db)
    service = SignalPerformanceService(db)
    service.update_future_price("sig-perf", "24h", 104)
    assert service.classify_buy_result("sig-perf") == "win"


def test_manual_feedback_is_stored_and_used(db) -> None:
    insert_signal(db, "sig-feedback")
    FeedbackService(db).mark("sig-feedback", "loss")
    row = db.query_one("SELECT final_result FROM signals WHERE id='sig-feedback'")
    feedback = db.query_one("SELECT result FROM manual_feedback WHERE signal_id='sig-feedback'")
    assert row["final_result"] == "loss"
    assert feedback["result"] == "loss"
