from __future__ import annotations

from app.scanner.scoring import ScoringEngine, score_label


def bullish_features() -> dict:
    return {
        "trend": "strong_uptrend",
        "relative_volume": 2.1,
        "breakout": {"detected": True},
        "rsi": 61,
        "macd_histogram": 0.8,
        "ema_alignment": "bullish",
        "btc_trend": "bullish",
        "eth_trend": "bullish",
        "volume_usdt": 25_000_000,
        "knowledge_score": 1,
        "change_24h": 5,
        "distance_to_resistance_pct": 3,
        "breakdown": {"detected": False},
        "failed_breakout": {"detected": False},
        "atr_pct": 2,
    }


def test_buy_score_reaches_strong_signal() -> None:
    score, reasons = ScoringEngine().buy_score(bullish_features())
    assert score >= 81
    assert score_label(score) == "Strong signal"
    assert "trend alignment" in reasons


def test_sell_score_uses_breakdown_and_failed_breakout() -> None:
    features = bullish_features()
    features.update(
        {
            "trend": "strong_downtrend",
            "breakdown": {"detected": True},
            "failed_breakout": {"detected": True},
            "macd_histogram": -0.7,
            "rsi": 76,
            "btc_trend": "bearish",
            "eth_trend": "bearish",
            "distance_to_resistance_pct": 0.5,
        }
    )
    score, reasons = ScoringEngine().sell_score(features)
    assert score >= 70
    assert "support breakdown" in reasons
    assert "failed breakout risk" in reasons


def test_high_risk_score_flags_low_liquidity_pump() -> None:
    features = bullish_features()
    features.update({"change_24h": 24, "relative_volume": 4, "volume_usdt": 500_000, "rsi": 84, "atr_pct": 9})
    score, reasons = ScoringEngine().high_risk_score(features)
    assert score >= 65
    assert "low-liquidity trap risk" in reasons
