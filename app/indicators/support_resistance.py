from __future__ import annotations

from statistics import mean


def swing_levels(candles: list[dict[str, float]], lookback: int = 3) -> dict[str, list[float]]:
    supports: list[float] = []
    resistances: list[float] = []
    if len(candles) < lookback * 2 + 1:
        return {"supports": supports, "resistances": resistances}
    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        low = float(candles[index]["low"])
        high = float(candles[index]["high"])
        if low == min(float(item["low"]) for item in window):
            supports.append(low)
        if high == max(float(item["high"]) for item in window):
            resistances.append(high)
    return {"supports": _cluster_levels(supports), "resistances": _cluster_levels(resistances)}


def _cluster_levels(levels: list[float], tolerance_pct: float = 0.45) -> list[float]:
    if not levels:
        return []
    levels = sorted(levels)
    clusters: list[list[float]] = [[levels[0]]]
    for level in levels[1:]:
        anchor = mean(clusters[-1])
        if anchor and abs(level - anchor) / anchor * 100 <= tolerance_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    return [mean(cluster) for cluster in clusters]


def nearest_levels(candles: list[dict[str, float]], price: float | None = None) -> dict[str, float | None]:
    if not candles:
        return {"support": None, "resistance": None}
    price = float(price if price is not None else candles[-1]["close"])
    levels = swing_levels(candles)
    supports = [level for level in levels["supports"] if level <= price]
    resistances = [level for level in levels["resistances"] if level >= price]
    return {
        "support": max(supports) if supports else min(float(item["low"]) for item in candles[-30:]),
        "resistance": min(resistances) if resistances else max(float(item["high"]) for item in candles[-30:]),
    }


def distance_pct(price: float, level: float | None) -> float | None:
    if level is None or price == 0:
        return None
    return (price - level) / price * 100
