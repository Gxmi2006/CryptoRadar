from __future__ import annotations

from typing import Any


def clamp(value: float, low: float = 0, high: float = 100) -> int:
    return int(max(low, min(high, round(value))))


def score_label(score: int) -> str:
    if score <= 30:
        return "Avoid"
    if score <= 50:
        return "Weak"
    if score <= 65:
        return "Watchlist"
    if score <= 80:
        return "Good signal"
    return "Strong signal"


class ScoringEngine:
    def __init__(self, adaptive_weights: dict[str, float] | None = None):
        self.weights = adaptive_weights or {}

    def buy_score(self, features: dict[str, Any]) -> tuple[int, list[str]]:
        score = 20.0
        reasons: list[str] = []
        score += self._add(features.get("trend") in {"strong_uptrend", "uptrend"}, 14, "trend alignment", reasons)
        score += self._add(float(features.get("relative_volume") or 1) >= 1.4, 12, "volume confirmation", reasons)
        score += self._add(features.get("breakout", {}).get("detected"), 13, "breakout strength", reasons)
        score += self._add(
            float(features.get("change_4h") or 0) >= 2 and float(features.get("relative_volume") or 1) >= 1.5,
            10,
            "strong trend continuation",
            reasons,
        )
        score += self._add(45 <= float(features.get("rsi") or 50) <= 68, 10, "RSI supports momentum without extremes", reasons)
        score += self._add(float(features.get("macd_histogram") or 0) > 0, 8, "MACD confirmation", reasons)
        score += self._add(features.get("ema_alignment") == "bullish", 9, "bullish EMA structure", reasons)
        score += self._add(features.get("btc_trend") != "bearish", 6, "BTC trend is not hostile", reasons)
        score += self._add(features.get("eth_trend") != "bearish", 4, "ETH trend is not hostile", reasons)
        score += self._add(float(features.get("volume_usdt") or 0) >= 5_000_000, 6, "acceptable liquidity", reasons)
        score += self._add(2 <= float(features.get("change_24h") or 0) <= 12, 6, "positive but not extreme 24h momentum", reasons)
        score += self._add(float(features.get("knowledge_score") or 0) > 0, 4, "knowledge-source confirmation", reasons)
        if float(features.get("change_24h") or 0) <= -4:
            score -= 12
            reasons.append("24h trend is weak")
        if features.get("breakdown", {}).get("detected"):
            score -= 10
            reasons.append("breakdown pressure reduces buy quality")
        if float(features.get("rsi") or 50) > 78:
            score -= 14
            reasons.append("RSI is too extended")
        if features.get("btc_trend") == "bearish":
            score -= 10
            reasons.append("BTC weakness penalizes altcoin buy setup")
        score += float(self.weights.get("buy_bias", 0))
        return clamp(score), reasons

    def sell_score(self, features: dict[str, Any]) -> tuple[int, list[str]]:
        score = 18.0
        reasons: list[str] = []
        score += self._add(features.get("trend") in {"strong_downtrend", "downtrend"}, 12, "momentum weakening", reasons)
        score += self._add(features.get("breakdown", {}).get("detected"), 15, "support breakdown", reasons)
        score += self._add(features.get("failed_breakout", {}).get("detected"), 12, "failed breakout risk", reasons)
        score += self._add(float(features.get("macd_histogram") or 0) < 0, 9, "MACD bearish pressure", reasons)
        score += self._add(float(features.get("rsi") or 50) >= 72, 8, "RSI overbought", reasons)
        score += self._add(float(features.get("relative_volume") or 1) >= 1.5, 7, "sell volume increasing", reasons)
        score += self._add(float(features.get("change_24h") or 0) <= -4, 8, "24h trend is weak", reasons)
        score += self._add(float(features.get("change_24h") or 0) <= -8, 10, "sharp 24h downside", reasons)
        score += self._add(float(features.get("change_4h") or 0) <= -4, 8, "4h downside continuation", reasons)
        score += self._add(features.get("btc_trend") == "bearish", 7, "BTC weakness", reasons)
        score += self._add(features.get("eth_trend") == "bearish", 4, "ETH weakness", reasons)
        score += self._add(float(features.get("distance_to_resistance_pct") or 99) <= 1.0, 7, "near resistance/profit-taking area", reasons)
        score += float(self.weights.get("sell_bias", 0))
        return clamp(score), reasons

    def hold_score(self, features: dict[str, Any]) -> tuple[int, list[str]]:
        score = 35.0
        reasons: list[str] = []
        score += self._add(features.get("trend") in {"uptrend", "strong_uptrend"}, 10, "trend remains constructive", reasons)
        score += self._add(40 <= float(features.get("rsi") or 50) <= 65, 8, "RSI is balanced", reasons)
        score += self._add(abs(float(features.get("change_24h") or 0)) < 4, 8, "price action is stable", reasons)
        score += self._add(features.get("ema_alignment") in {"bullish", "mixed"}, 7, "EMA structure is not broken", reasons)
        return clamp(score), reasons

    def high_risk_score(self, features: dict[str, Any]) -> tuple[int, list[str]]:
        score = 10.0
        reasons: list[str] = []
        score += self._add(float(features.get("change_24h") or 0) >= 15, 18, "large 24h pump", reasons)
        score += self._add(float(features.get("change_24h") or 0) >= 25, 12, "extreme meme-style pump", reasons)
        score += self._add(float(features.get("relative_volume") or 1) >= 2.5, 16, "abnormal volume spike", reasons)
        score += self._add(float(features.get("volume_usdt") or 0) < 2_000_000, 14, "low-liquidity trap risk", reasons)
        score += self._add(float(features.get("rsi") or 50) >= 80, 14, "overbought pump", reasons)
        score += self._add(features.get("failed_breakout", {}).get("detected"), 15, "fake breakout risk", reasons)
        score += self._add(float(features.get("atr_pct") or 0) >= 8, 10, "abnormal volatility", reasons)
        return clamp(score), reasons

    @staticmethod
    def _add(condition: bool, points: float, reason: str, reasons: list[str]) -> float:
        if condition:
            reasons.append(reason)
            return points
        return 0.0
