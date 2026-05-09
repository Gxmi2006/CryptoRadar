from __future__ import annotations


def trend_from_snapshot(snapshot: dict) -> str:
    change = float(snapshot.get("change_24h") or 0)
    if change > 2:
        return "bullish"
    if change < -2:
        return "bearish"
    return "sideways"


def detect_trend(indicators: dict, structure: dict, snapshot: dict) -> dict:
    ema_alignment = indicators.get("ema_alignment")
    market_structure = structure.get("trend")
    snapshot_trend = trend_from_snapshot(snapshot)
    if ema_alignment == "bullish" and market_structure == "uptrend":
        trend = "strong_uptrend"
    elif ema_alignment == "bearish" and market_structure == "downtrend":
        trend = "strong_downtrend"
    elif snapshot_trend == "bullish":
        trend = "uptrend"
    elif snapshot_trend == "bearish":
        trend = "downtrend"
    else:
        trend = "sideways"
    return {"trend": trend, "ema_alignment": ema_alignment, "market_structure": market_structure}
