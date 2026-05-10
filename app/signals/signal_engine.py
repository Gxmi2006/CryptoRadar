from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.ai.signal_analyzer import LocalAISignalAnalyzer
from app.indicators.indicators import analyze_indicators
from app.indicators.market_structure import classify_structure
from app.indicators.support_resistance import distance_pct, nearest_levels
from app.learning.adaptive_scoring import AdaptiveScoringEngine
from app.learning.ml_model import FutureMLModel
from app.scanner.breakout_detector import detect_breakdown, detect_breakout, detect_failed_breakout
from app.scanner.scoring import ScoringEngine, score_label
from app.scanner.trend_detector import detect_trend, trend_from_snapshot
from app.signals.buy_signal_engine import BuySignalEngine
from app.signals.hold_signal_engine import HoldSignalEngine
from app.signals.risk_engine import RiskEngine
from app.signals.sell_signal_engine import SellSignalEngine


class SignalEngine:
    def __init__(self, config: dict[str, Any], db: Any):
        self.config = config
        adaptive = AdaptiveScoringEngine(db, config).load_weights()
        scoring = ScoringEngine(adaptive)
        self.buy = BuySignalEngine(scoring)
        self.sell = SellSignalEngine(scoring)
        self.hold = HoldSignalEngine(scoring)
        self.risk = RiskEngine(scoring)
        self.ai = LocalAISignalAnalyzer(config)
        self.ml = FutureMLModel(db, config)

    def analyze_symbol(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        candle_map: dict[str, list[dict[str, float]]],
        btc_context: dict[str, Any],
        eth_context: dict[str, Any],
        knowledge_chunks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        timeframe = self._primary_timeframe(candle_map)
        candles = candle_map.get(timeframe) or []
        if len(candles) < 30:
            return None

        indicators = analyze_indicators(candles)
        price = float(snapshot.get("price") or indicators.get("price") or candles[-1]["close"])
        levels = nearest_levels(candles, price)
        structure = classify_structure(candles)
        trend = detect_trend(indicators, structure, snapshot)
        breakout = detect_breakout(price, levels, indicators)
        breakdown = detect_breakdown(price, levels, indicators)
        failed_breakout = detect_failed_breakout(price, levels, indicators)
        btc_trend = trend_from_snapshot(btc_context) if btc_context else "unknown"
        eth_trend = trend_from_snapshot(eth_context) if eth_context else "unknown"
        knowledge_score = self._knowledge_score(knowledge_chunks)

        features = {
            **snapshot,
            **indicators,
            "trend": trend["trend"],
            "market_structure": structure,
            "support": levels["support"],
            "resistance": levels["resistance"],
            "distance_to_support_pct": distance_pct(price, levels["support"]),
            "distance_to_resistance_pct": abs(distance_pct(price, levels["resistance"]) or 99),
            "breakout": breakout,
            "breakdown": breakdown,
            "failed_breakout": failed_breakout,
            "btc_trend": btc_trend,
            "eth_trend": eth_trend,
            "knowledge_score": knowledge_score,
        }

        buy_score, buy_reasons = self.buy.score(features)
        sell_score, sell_reasons = self.sell.score(features)
        hold_score, hold_reasons = self.hold.score(features)
        high_risk_score, risk_reasons = self.risk.score_high_risk(features)

        signal_type, score, reasons = self._choose_signal(
            buy_score,
            sell_score,
            hold_score,
            high_risk_score,
            buy_reasons,
            sell_reasons,
            hold_reasons,
            risk_reasons,
        )
        confidence = self._confidence(score)
        risk_level = self._risk_level(high_risk_score, indicators)
        zones = self._zones(price, levels, indicators)
        warning = self._warning(signal_type, high_risk_score, risk_reasons)
        main_reason = "; ".join(reasons[:3]) if reasons else "No strong confirmation yet"

        context = {
            "symbol": symbol,
            "signal_type": signal_type,
            "score": score,
            "confidence": confidence,
            "timeframe": timeframe,
            "trend": trend["trend"],
            "relative_volume": float(indicators.get("relative_volume") or 1),
            "risk_level": risk_level,
            "main_reason": main_reason,
            "rsi": indicators.get("rsi"),
            "macd_histogram": indicators.get("macd_histogram"),
            "invalidation_level": zones["invalidation_level"],
            "possible_entry_zone": zones["possible_entry_zone"],
            "possible_take_profit_zones": zones["possible_take_profit_zones"],
            "possible_stop_loss_zone": zones["possible_stop_loss_zone"],
            "warning": warning,
        }
        ai_text = self.ai.analyze(context, knowledge_chunks)
        signal_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{symbol}-{uuid4().hex[:8]}"
        signal = {
            "id": signal_id,
            "symbol": symbol,
            "signal_type": signal_type,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "price": price,
            "score": score,
            "score_label": score_label(score),
            "confidence": confidence,
            "risk_level": risk_level,
            "timeframe": timeframe,
            "main_reason": main_reason,
            "indicators": indicators,
            "features": features,
            "score_details": {
                "buy_score": buy_score,
                "sell_score": sell_score,
                "hold_score": hold_score,
                "wait_score": max(buy_score, sell_score, hold_score),
                "avoid_score": max(0, 100 - max(buy_score, sell_score, hold_score)),
                "high_risk_score": high_risk_score,
                "reasons": {
                    "buy": buy_reasons,
                    "sell": sell_reasons,
                    "hold": hold_reasons,
                    "high_risk": risk_reasons,
                },
            },
            "btc_trend": btc_trend,
            "eth_trend": eth_trend,
            "support_level": levels["support"],
            "resistance_level": levels["resistance"],
            **zones,
            "knowledge_sources_used": sorted({chunk.get("file_name", "unknown") for chunk in knowledge_chunks}),
            "ai_analysis": ai_text,
            "warning": warning,
            "final_note": "This is an analysis-based signal, not guaranteed profit. Decide manually.",
        }
        ml_prediction = self.ml.predict_for_signal(signal)
        if ml_prediction:
            signal["ml_prediction"] = ml_prediction
        return signal

    def _choose_signal(
        self,
        buy_score: int,
        sell_score: int,
        hold_score: int,
        high_risk_score: int,
        buy_reasons: list[str],
        sell_reasons: list[str],
        hold_reasons: list[str],
        risk_reasons: list[str],
    ) -> tuple[str, int, list[str]]:
        buy_threshold = int(self.config["scanner"].get("buy_score_threshold", 70))
        sell_threshold = int(self.config["scanner"].get("sell_score_threshold", 70))
        risk_threshold = int(self.config["scanner"].get("high_risk_threshold", 65))
        if high_risk_score >= risk_threshold and high_risk_score >= max(buy_score, sell_score):
            return "HIGH_RISK", high_risk_score, risk_reasons
        if sell_score >= sell_threshold and sell_score >= buy_score:
            return "SELL", sell_score, sell_reasons
        if buy_score >= buy_threshold:
            return "BUY", buy_score, buy_reasons
        if hold_score >= 55 and max(buy_score, sell_score) < 66:
            return "HOLD", hold_score, hold_reasons
        if max(buy_score, sell_score, hold_score) >= 45:
            return "WAIT", max(buy_score, sell_score, hold_score), ["setup is not confirmed yet"]
        return "AVOID", max(20, high_risk_score), ["weak setup or insufficient confirmation"]

    @staticmethod
    def _primary_timeframe(candle_map: dict[str, list[dict[str, float]]]) -> str:
        for timeframe in ("15m", "1h", "5m", "4h", "1d"):
            if timeframe in candle_map:
                return timeframe
        return next(iter(candle_map))

    @staticmethod
    def _knowledge_score(chunks: list[dict[str, Any]]) -> float:
        trust = {"High trust": 1.0, "Medium trust": 0.6, "Low trust": 0.25, "Experimental": 0.1}
        return sum(trust.get(chunk.get("trust_level", "Medium trust"), 0.4) for chunk in chunks[:5])

    @staticmethod
    def _confidence(score: int) -> str:
        if score >= 82:
            return "High"
        if score >= 66:
            return "Medium"
        return "Low"

    @staticmethod
    def _risk_level(high_risk_score: int, indicators: dict[str, Any]) -> str:
        if high_risk_score >= 75 or float(indicators.get("atr_pct") or 0) >= 8:
            return "High"
        if high_risk_score >= 50 or float(indicators.get("atr_pct") or 0) >= 4:
            return "Medium"
        return "Low"

    @staticmethod
    def _zones(price: float, levels: dict[str, float | None], indicators: dict[str, Any]) -> dict[str, Any]:
        support = levels.get("support") or price * 0.97
        resistance = levels.get("resistance") or price * 1.05
        atr_pct = float(indicators.get("atr_pct") or 2)
        buffer_pct = max(0.4, min(2.5, atr_pct / 3))
        entry_low = max(support, price * (1 - buffer_pct / 100))
        entry_high = price
        stop = support * 0.99
        tp1 = resistance
        tp2 = price + (price - stop) * 2 if price > stop else price * 1.04
        return {
            "possible_entry_zone": f"{entry_low:.8g}-{entry_high:.8g}",
            "possible_take_profit_zones": [round(tp1, 8), round(tp2, 8)],
            "possible_stop_loss_zone": round(stop, 8),
            "invalidation_level": round(stop, 8),
        }

    @staticmethod
    def _warning(signal_type: str, high_risk_score: int, reasons: list[str]) -> str:
        if signal_type == "BUY" and high_risk_score >= 55:
            return "Buying may be late; review manually and avoid chasing a pump."
        if signal_type == "HIGH_RISK":
            return "Risk is increasing; consider avoiding until volatility cools."
        if signal_type == "SELL":
            return "Sell warning only; decide manually and review support levels."
        if reasons:
            return reasons[0]
        return "This setup is not confirmed yet."
