from __future__ import annotations

from app.ai.telegram_message_formatter import TelegramMessageFormatter
from app.learning.ml_model import FutureMLModel, extract_ml_features
from app.mock.mock_market import MockMarket
from app.signals.signal_engine import SignalEngine


def sample_signal_payload() -> dict:
    return {
        "id": "sig-ml-1",
        "symbol": "LOWUSDT",
        "signal_type": "BUY",
        "price": 1.2,
        "score": 74,
        "confidence": "Medium",
        "risk_level": "Medium",
        "timeframe": "15m",
        "main_reason": "Breakout with volume",
        "indicators": {"rsi": 62, "macd_histogram": 0.2, "relative_volume": 1.8, "atr_pct": 3},
        "features": {"volume_usdt": 500_000, "change_1h": 1, "change_4h": 3, "change_24h": 6},
        "score_details": {"buy_score": 74, "sell_score": 20, "hold_score": 55, "high_risk_score": 40},
        "btc_trend": "bullish",
        "eth_trend": "sideways",
    }


def test_ml_training_examples_are_built_from_signal_history(config: dict, db) -> None:
    db.execute(
        "INSERT INTO symbol_data_quality(symbol, data_quality, quality_reasons_json, volume_usdt, candle_count) VALUES (?, ?, ?, ?, ?)",
        ("LOWUSDT", "low_volume", "[]", 500_000, 24),
    )
    payload = sample_signal_payload()
    db.execute(
        """
        INSERT INTO signals(id, symbol, signal_type, created_at, price, score, confidence, risk_level, timeframe, main_reason, payload_json, final_result)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["id"],
            payload["symbol"],
            payload["signal_type"],
            payload["price"],
            payload["score"],
            payload["confidence"],
            payload["risk_level"],
            payload["timeframe"],
            payload["main_reason"],
            db.dumps(payload),
            "win",
        ),
    )
    result = FutureMLModel(db, config).build_training_examples()
    assert result["examples"] == 1
    row = db.query_one("SELECT * FROM ml_training_examples WHERE signal_id='sig-ml-1'")
    assert row is not None
    features = db.loads(row["features_json"], {})
    assert features["data_quality"] == "low_volume"
    assert features["signal_buy"] == 1.0


def test_ml_training_handles_too_few_samples_safely(config: dict, db) -> None:
    config["ml"]["min_training_samples"] = 30
    report = FutureMLModel(db, config).train()
    assert "Need at least 30" in report


def test_extract_ml_features_uses_quality_label() -> None:
    features = extract_ml_features(sample_signal_payload(), {"data_quality": "low_volume"})
    assert features["data_quality"] == "low_volume"
    assert features["data_quality_score"] < 0.5


def test_signal_engine_attaches_prediction_when_model_available(config: dict, db) -> None:
    config["ai"]["enabled"] = False
    engine = SignalEngine(config, db)

    class FakeML:
        @staticmethod
        def predict_for_signal(signal: dict) -> dict:
            return {
                "success_probability": 0.64,
                "risk_score": 0.42,
                "confidence_score": 0.28,
                "data_quality": "good",
                "model_version": "test",
            }

    engine.ml = FakeML()
    market = MockMarket()
    signal = engine.analyze_symbol(
        "SOLUSDT",
        market.snapshots()["SOLUSDT"],
        market.candles("SOLUSDT"),
        market.snapshots()["BTCUSDT"],
        market.snapshots()["ETHUSDT"],
        [],
    )
    assert signal is not None
    assert signal["ml_prediction"]["success_probability"] == 0.64


def test_telegram_template_includes_ml_note(config: dict) -> None:
    signal = sample_signal_payload()
    signal["ml_prediction"] = {
        "success_probability": 0.64,
        "risk_score": 0.42,
        "confidence_score": 0.28,
        "data_quality": "low_volume",
        "model_version": "test",
    }
    text = TelegramMessageFormatter(config).format(signal)
    assert "ML filter:" in text
    assert "64% success probability" in text
