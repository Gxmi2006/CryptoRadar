from __future__ import annotations

from app.indicators.indicators import analyze_indicators, ema, macd, rsi
from app.indicators.support_resistance import nearest_levels, swing_levels


def candles(values: list[float]) -> list[dict[str, float]]:
    rows = []
    for index, value in enumerate(values):
        rows.append(
            {
                "open_time": index,
                "open": value * 0.995,
                "high": value * 1.01,
                "low": value * 0.99,
                "close": value,
                "volume": 100 + index,
                "close_time": index + 1,
            }
        )
    return rows


def test_rsi_ema_macd_calculation() -> None:
    values = [float(index) for index in range(1, 80)]
    assert rsi(values) > 90
    assert ema(values, 9) is not None
    assert macd(values)["histogram"] is not None


def test_indicator_snapshot_contains_requested_fields() -> None:
    snapshot = analyze_indicators(candles([float(index) for index in range(1, 230)]))
    assert snapshot["ema_9"] > snapshot["ema_21"] > snapshot["ema_50"]
    assert snapshot["ema_alignment"] == "bullish"
    assert "bollinger" in snapshot
    assert snapshot["relative_volume"] > 0


def test_support_resistance_detection() -> None:
    data = candles([10, 11, 12, 11, 10, 11, 13, 12, 11, 12, 14, 13, 12, 13, 15])
    levels = swing_levels(data, lookback=1)
    nearest = nearest_levels(data, price=13.5)
    assert levels["supports"]
    assert levels["resistances"]
    assert nearest["support"] is not None
    assert nearest["resistance"] is not None
