from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.backtest.backtester import BacktestEngine, baseline_signals, evaluate_signal_outcome
from app.backtest.signal_quality_report import SignalQualityReport


def test_backtest_handles_insufficient_candles(config: dict, db) -> None:
    report = BacktestEngine(config, db).run(symbol="SOLUSDT")
    assert "not enough stored candles" in report
    run = db.query_one("SELECT status FROM backtest_runs ORDER BY created_at DESC LIMIT 1")
    assert run is not None
    assert run["status"] == "insufficient_data"


def test_buy_sell_and_high_risk_outcomes() -> None:
    buy = {"symbol": "SOLUSDT", "signal_type": "BUY", "price": 100, "possible_take_profit_zones": [103], "invalidation_level": 98}
    sell = {"symbol": "SOLUSDT", "signal_type": "SELL", "price": 100}
    high_risk = {"symbol": "SOLUSDT", "signal_type": "HIGH_RISK", "price": 100}
    future_up = [{"open": 100, "high": 103.5, "low": 99, "close": 102, "volume": 100, "open_time": 1, "close_time": 2}]
    future_down = [{"open": 100, "high": 100.5, "low": 96, "close": 97, "volume": 100, "open_time": 1, "close_time": 2}]

    assert evaluate_signal_outcome(buy, future_up)["success"] is True
    assert evaluate_signal_outcome(sell, future_down)["success"] is True
    assert evaluate_signal_outcome(high_risk, future_down)["success"] is True


def test_backtest_generates_baseline_comparison(config: dict, db) -> None:
    insert_candles(db, "SOLUSDT", slope=0.2, volume_spike=True)
    insert_candles(db, "BTCUSDT", slope=0.03)
    insert_candles(db, "ETHUSDT", slope=0.02)
    db.execute(
        "INSERT INTO symbol_data_quality(symbol, data_quality, quality_reasons_json, volume_usdt, candle_count) VALUES (?, ?, ?, ?, ?)",
        ("SOLUSDT", "good", "[]", 10_000_000, 280),
    )
    config["backtest"]["lookback_candles"] = 60
    config["backtest"]["default_days"] = 5
    config["backtest"]["max_symbols"] = 3

    report = BacktestEngine(config, db).run(symbol="SOLUSDT")

    assert "Strategy comparison" in report
    baseline = db.query_one("SELECT COUNT(*) AS count FROM backtest_results WHERE strategy!='cryptoradar'")
    assert baseline is not None
    assert baseline["count"] > 0


def test_signal_quality_report_works_without_and_with_backtest(config: dict, db) -> None:
    empty_report = SignalQualityReport(config, db).render()
    assert "No backtest run yet" in empty_report

    insert_candles(db, "SOLUSDT", slope=0.08, volume_spike=True)
    config["backtest"]["lookback_candles"] = 60
    config["backtest"]["default_days"] = 5
    BacktestEngine(config, db).run(symbol="SOLUSDT")

    report = SignalQualityReport(config, db).render()
    assert "Latest backtest" in report
    assert "Run ID:" in report


def test_backtest_does_not_call_external_ai_or_telegram(config: dict, db, monkeypatch) -> None:
    insert_candles(db, "SOLUSDT", slope=0.08, volume_spike=True)
    config["backtest"]["lookback_candles"] = 60
    config["backtest"]["default_days"] = 5
    config["ai"]["enabled"] = True
    config["ai"]["provider"] = "lmstudio"
    config["notifications"]["telegram_enabled"] = True

    def fail_external(*args, **kwargs):
        raise AssertionError("external service should not be called during backtest")

    monkeypatch.setattr("app.ai.lmstudio_client.LMStudioClient.chat", fail_external)
    monkeypatch.setattr("app.notifications.telegram.TelegramNotifier.send", fail_external)

    report = BacktestEngine(config, db).run(symbol="SOLUSDT")
    assert "CryptoRadar Backtest Report" in report or "not enough stored candles" in report


def test_baseline_signals_are_deterministic() -> None:
    candles = make_candles("SOLUSDT", slope=0.2, volume_spike=True, count=80)
    first = baseline_signals("SOLUSDT", candles, "15m")
    second = baseline_signals("SOLUSDT", candles, "15m")
    assert first == second
    assert any(signal["strategy"] in {"momentum_baseline", "volume_spike_baseline", "random_baseline"} for signal in first)


def insert_candles(db, symbol: str, slope: float = 0.0, volume_spike: bool = False) -> None:
    rows = []
    for candle in make_candles(symbol, slope=slope, volume_spike=volume_spike, count=280):
        rows.append(
            (
                symbol,
                "15m",
                candle["open_time"],
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
                candle["close_time"],
            )
        )
    db.executemany(
        """
        INSERT INTO candles(symbol, interval, open_time, open, high, low, close, volume, close_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def make_candles(symbol: str, slope: float = 0.0, volume_spike: bool = False, count: int = 280) -> list[dict[str, float]]:
    del symbol
    start = datetime.now(timezone.utc) - timedelta(minutes=15 * count)
    price = 100.0
    candles: list[dict[str, float]] = []
    for index in range(count):
        open_price = price
        close = price * (1 + slope / 100)
        high = max(open_price, close) * 1.004
        low = min(open_price, close) * 0.996
        volume = 1000.0
        if volume_spike and index % 18 == 0:
            volume = 5000.0
        open_time = int((start + timedelta(minutes=15 * index)).timestamp() * 1000)
        candles.append(
            {
                "open_time": open_time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "close_time": open_time + 15 * 60 * 1000 - 1,
            }
        )
        price = close
    return candles
