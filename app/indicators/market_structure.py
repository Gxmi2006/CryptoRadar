from __future__ import annotations

from app.indicators.support_resistance import swing_levels


def classify_structure(candles: list[dict[str, float]]) -> dict[str, object]:
    levels = swing_levels(candles)
    highs = levels["resistances"][-4:]
    lows = levels["supports"][-4:]
    higher_highs = len(highs) >= 2 and highs[-1] > highs[-2]
    higher_lows = len(lows) >= 2 and lows[-1] > lows[-2]
    lower_highs = len(highs) >= 2 and highs[-1] < highs[-2]
    lower_lows = len(lows) >= 2 and lows[-1] < lows[-2]
    if higher_highs and higher_lows:
        trend = "uptrend"
    elif lower_highs and lower_lows:
        trend = "downtrend"
    else:
        trend = "sideways"
    return {
        "trend": trend,
        "higher_highs": higher_highs,
        "higher_lows": higher_lows,
        "lower_highs": lower_highs,
        "lower_lows": lower_lows,
        "swing_highs": highs,
        "swing_lows": lows,
    }
