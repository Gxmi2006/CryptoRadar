from __future__ import annotations


def detect_breakout(price: float, levels: dict, indicators: dict) -> dict:
    resistance = levels.get("resistance")
    rel_volume = float(indicators.get("relative_volume") or 1)
    if resistance and price > resistance and rel_volume >= 1.4:
        strength = (price - resistance) / resistance * 100 * rel_volume
        return {"detected": True, "type": "breakout", "strength": strength, "level": resistance}
    return {"detected": False, "type": "", "strength": 0.0, "level": resistance}


def detect_breakdown(price: float, levels: dict, indicators: dict) -> dict:
    support = levels.get("support")
    rel_volume = float(indicators.get("relative_volume") or 1)
    if support and price < support and rel_volume >= 1.3:
        strength = (support - price) / support * 100 * rel_volume
        return {"detected": True, "type": "breakdown", "strength": strength, "level": support}
    return {"detected": False, "type": "", "strength": 0.0, "level": support}


def detect_failed_breakout(price: float, levels: dict, indicators: dict) -> dict:
    resistance = levels.get("resistance")
    wick = indicators.get("wick_strength") or {}
    upper_wick = float(wick.get("upper") or 0)
    if resistance and price < resistance and upper_wick > 0.45 and float(indicators.get("relative_volume") or 1) > 1.5:
        return {"detected": True, "reason": "rejection wick near resistance on high volume", "level": resistance}
    return {"detected": False, "reason": "", "level": resistance}
