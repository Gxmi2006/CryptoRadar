from __future__ import annotations

from app.learning.paper_trade_tracker import PaperTradeTracker


def buy_signal() -> dict:
    return {
        "id": "sig-paper",
        "symbol": "SOLUSDT",
        "signal_type": "BUY",
        "price": 100.0,
        "possible_entry_zone": "98-100",
        "possible_take_profit_zones": [110.0, 120.0],
        "possible_stop_loss_zone": 95.0,
        "invalidation_level": 95.0,
    }


def test_paper_trade_hits_take_profit(db, config: dict) -> None:
    db.execute(
        """
        INSERT INTO signals(id, symbol, signal_type, created_at, price, score, confidence, risk_level, timeframe, main_reason, payload_json)
        VALUES ('sig-paper', 'SOLUSDT', 'BUY', CURRENT_TIMESTAMP, 100, 75, 'Medium', 'Medium', '15m', 'test', '{}')
        """
    )
    tracker = PaperTradeTracker(db, config)
    trade_id = tracker.create_for_signal(buy_signal())
    row = tracker.update_with_price(trade_id, 111.0)
    assert row["result"] == "win"
    perf = db.query_one("SELECT final_result FROM signal_performance WHERE signal_id='sig-paper'")
    assert perf["final_result"] == "win"
