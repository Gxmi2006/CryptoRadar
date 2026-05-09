from __future__ import annotations

from statistics import mean, pstdev
from typing import Any


def closes(candles: list[dict[str, float]]) -> list[float]:
    return [float(item["close"]) for item in candles]


def highs(candles: list[dict[str, float]]) -> list[float]:
    return [float(item["high"]) for item in candles]


def lows(candles: list[dict[str, float]]) -> list[float]:
    return [float(item["low"]) for item in candles]


def volumes(candles: list[dict[str, float]]) -> list[float]:
    return [float(item.get("volume", 0)) for item in candles]


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    return mean(values[-period:])


def ema_series(values: list[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value * alpha) + (result[-1] * (1 - alpha)))
    return result


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if len(series) >= period else None


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[-period - 1 : -1], values[-period:]):
        delta = current - prev
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float | None]:
    if len(values) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    fast_ema = ema_series(values, fast)
    slow_ema = ema_series(values, slow)
    offset = len(fast_ema) - len(slow_ema)
    macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]
    signal_line = ema_series(macd_line, signal)
    histogram = macd_line[-1] - signal_line[-1]
    return {"macd": macd_line[-1], "signal": signal_line[-1], "histogram": histogram}


def bollinger_bands(values: list[float], period: int = 20, deviations: float = 2.0) -> dict[str, float | None]:
    if len(values) < period:
        return {"middle": None, "upper": None, "lower": None, "width_pct": None}
    window = values[-period:]
    middle = mean(window)
    deviation = pstdev(window) if len(window) > 1 else 0
    upper = middle + deviations * deviation
    lower = middle - deviations * deviation
    width_pct = ((upper - lower) / middle * 100) if middle else 0
    return {"middle": middle, "upper": upper, "lower": lower, "width_pct": width_pct}


def atr(candles: list[dict[str, float]], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    true_ranges: list[float] = []
    for prev, current in zip(candles[-period - 1 : -1], candles[-period:]):
        high = float(current["high"])
        low = float(current["low"])
        prev_close = float(prev["close"])
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(true_ranges)


def relative_volume(candles: list[dict[str, float]], period: int = 20) -> float:
    vols = volumes(candles)
    if len(vols) <= period:
        return 1.0
    baseline = mean(vols[-period - 1 : -1])
    return (vols[-1] / baseline) if baseline else 1.0


def candle_body_strength(candle: dict[str, float]) -> float:
    high = float(candle["high"])
    low = float(candle["low"])
    spread = high - low
    if spread <= 0:
        return 0.0
    return abs(float(candle["close"]) - float(candle["open"])) / spread


def candle_wick_strength(candle: dict[str, float]) -> dict[str, float]:
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close_price = float(candle["close"])
    spread = high - low
    if spread <= 0:
        return {"upper": 0.0, "lower": 0.0}
    upper = high - max(open_price, close_price)
    lower = min(open_price, close_price) - low
    return {"upper": upper / spread, "lower": lower / spread}


def analyze_indicators(candles: list[dict[str, float]]) -> dict[str, Any]:
    values = closes(candles)
    last_candle = candles[-1] if candles else {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
    macd_data = macd(values)
    bb = bollinger_bands(values)
    ema9 = ema(values, 9)
    ema21 = ema(values, 21)
    ema50 = ema(values, 50)
    ema200 = ema(values, 200)
    ema_alignment = "unknown"
    if all(value is not None for value in (ema9, ema21, ema50)):
        if ema9 > ema21 > ema50:
            ema_alignment = "bullish"
        elif ema9 < ema21 < ema50:
            ema_alignment = "bearish"
        else:
            ema_alignment = "mixed"
    atr_value = atr(candles)
    price = values[-1] if values else 0
    return {
        "price": price,
        "rsi": rsi(values),
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_histogram": macd_data["histogram"],
        "ema_9": ema9,
        "ema_21": ema21,
        "ema_50": ema50,
        "ema_200": ema200,
        "sma_20": sma(values, 20),
        "sma_50": sma(values, 50),
        "bollinger": bb,
        "atr": atr_value,
        "atr_pct": (atr_value / price * 100) if atr_value and price else 0,
        "relative_volume": relative_volume(candles),
        "volume_ma": sma(volumes(candles), 20),
        "ema_alignment": ema_alignment,
        "body_strength": candle_body_strength(last_candle),
        "wick_strength": candle_wick_strength(last_candle),
    }
