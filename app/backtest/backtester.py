from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from uuid import uuid4

from app.indicators.indicators import analyze_indicators
from app.signals.signal_engine import SignalEngine


ALERT_TYPES = {"BUY", "SELL", "HIGH_RISK"}


class BacktestEngine:
    """Replay CryptoRadar signals against stored candles only."""

    def __init__(self, config: dict[str, Any], db: Any):
        self.config = config
        self.db = db

    def run(
        self,
        symbol: str | None = None,
        timeframe: str | None = None,
        days: int | None = None,
        max_symbols: int | None = None,
    ) -> str:
        cfg = self.config.get("backtest", {})
        if not cfg.get("enabled", True):
            return "Backtesting is disabled in config."
        timeframe = timeframe or str(cfg.get("default_timeframe", "15m"))
        days = int(days if days is not None else cfg.get("default_days", 30))
        lookback = int(cfg.get("lookback_candles", 220))
        max_symbols = int(max_symbols if max_symbols is not None else cfg.get("max_symbols", 50))
        horizons = [str(item) for item in cfg.get("horizons", ["1h", "4h", "24h"])]
        max_horizon = max(horizon_to_candles(horizon, timeframe) for horizon in horizons)
        run_id = f"bt-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"

        self._create_run(run_id, timeframe, days, max_symbols, symbol, lookback, horizons)
        candles_by_symbol = self._load_candles(timeframe, days, max_symbols, symbol)
        usable_symbols = [
            item
            for item, candles in candles_by_symbol.items()
            if len(candles) >= lookback + max_horizon + 1
        ]
        if not usable_symbols:
            report = (
                "Backtest could not run: not enough stored candles. "
                "Leave .\\scripts\\run_cryptoradar.ps1 running longer or run python main.py --collect-market-data-now."
            )
            self._finish_run(run_id, "insufficient_data", 0, report, {"symbols_loaded": len(candles_by_symbol)})
            return report

        safe_config = self._safe_backtest_config()
        engine = SignalEngine(safe_config, self.db)
        rows: list[dict[str, Any]] = []
        for current_symbol in usable_symbols:
            candles = candles_by_symbol[current_symbol]
            rows.extend(self._replay_symbol(run_id, engine, current_symbol, candles, candles_by_symbol, timeframe, lookback, max_horizon))

        self._save_results(rows)
        summary = self._summarize_run(run_id)
        status = "ok" if rows else "no_signals"
        report = format_backtest_report(summary)
        self._finish_run(run_id, status, len(rows), report, summary)
        return report

    def _safe_backtest_config(self) -> dict[str, Any]:
        cfg = copy.deepcopy(self.config)
        cfg.setdefault("ai", {})["enabled"] = False
        cfg.setdefault("ml", {})["enabled"] = False
        notifications = cfg.setdefault("notifications", {})
        for key in ("telegram_enabled", "desktop_enabled", "email_enabled", "discord_enabled", "notify_startup", "notify_errors"):
            notifications[key] = False
        return cfg

    def _load_candles(
        self,
        timeframe: str,
        days: int,
        max_symbols: int,
        symbol: str | None,
    ) -> dict[str, list[dict[str, float]]]:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        params: list[Any] = [timeframe, cutoff]
        where = "WHERE interval=? AND open_time >= ?"
        if symbol:
            where += " AND symbol=?"
            params.append(symbol.upper())
        symbols = self.db.query(
            f"""
            SELECT symbol, COUNT(*) AS count
            FROM candles
            {where}
            GROUP BY symbol
            ORDER BY count DESC, symbol ASC
            LIMIT ?
            """,
            [*params, max_symbols],
        )
        result: dict[str, list[dict[str, float]]] = {}
        for row in symbols:
            result[row["symbol"]] = self._load_symbol_candles(row["symbol"], timeframe, cutoff)
        return result

    def _load_symbol_candles(self, symbol: str, timeframe: str, cutoff: int) -> list[dict[str, float]]:
        rows = self.db.query(
            """
            SELECT open_time, open, high, low, close, volume, close_time
            FROM candles
            WHERE symbol=? AND interval=? AND open_time >= ?
            ORDER BY open_time ASC
            """,
            (symbol, timeframe, cutoff),
        )
        return [
            {
                "open_time": int(row["open_time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "close_time": int(row["close_time"]),
            }
            for row in rows
        ]

    def _replay_symbol(
        self,
        run_id: str,
        engine: SignalEngine,
        symbol: str,
        candles: list[dict[str, float]],
        candles_by_symbol: dict[str, list[dict[str, float]]],
        timeframe: str,
        lookback: int,
        max_horizon: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        step = max(1, min(max_horizon, 4))
        for index in range(lookback - 1, len(candles) - max_horizon, step):
            window = candles[index - lookback + 1 : index + 1]
            future = candles[index + 1 : index + max_horizon + 1]
            snapshot = snapshot_from_window(window, timeframe)
            btc_context = context_at("BTCUSDT", candles_by_symbol, candles[index]["open_time"], timeframe, lookback)
            eth_context = context_at("ETHUSDT", candles_by_symbol, candles[index]["open_time"], timeframe, lookback)
            signal = engine.analyze_symbol(symbol, snapshot, {timeframe: window}, btc_context, eth_context, [])
            if signal and signal.get("signal_type") in ALERT_TYPES:
                results.append(self._result_row(run_id, "cryptoradar", signal, timeframe, candles[index]["open_time"], future))
            for baseline in baseline_signals(symbol, window, timeframe):
                results.append(self._result_row(run_id, baseline["strategy"], baseline, timeframe, candles[index]["open_time"], future))
        return results

    def _result_row(
        self,
        run_id: str,
        strategy: str,
        signal: dict[str, Any],
        timeframe: str,
        open_time: int,
        future: list[dict[str, float]],
    ) -> dict[str, Any]:
        outcome = evaluate_signal_outcome(signal, future)
        quality = self.db.query_one("SELECT data_quality FROM symbol_data_quality WHERE symbol=?", (signal["symbol"],))
        data_quality = quality["data_quality"] if quality else "unknown"
        return {
            "run_id": run_id,
            "strategy": strategy,
            "symbol": signal["symbol"],
            "signal_type": signal["signal_type"],
            "score": int(signal.get("score") or 0),
            "timeframe": timeframe,
            "open_time": int(open_time),
            "price": float(signal.get("price") or 0),
            "future_return_pct": outcome["future_return_pct"],
            "max_favorable_pct": outcome["max_favorable_pct"],
            "max_drawdown_pct": outcome["max_drawdown_pct"],
            "success": 1 if outcome["success"] else 0,
            "false_positive": 1 if not outcome["success"] else 0,
            "data_quality": data_quality,
            "payload": {"signal": compact_signal(signal), "outcome": outcome},
        }

    def _create_run(
        self,
        run_id: str,
        timeframe: str,
        days: int,
        max_symbols: int,
        symbol: str | None,
        lookback: int,
        horizons: list[str],
    ) -> None:
        self.db.execute(
            """
            INSERT INTO backtest_runs(
                id, timeframe, days, max_symbols, symbol_filter, lookback_candles,
                horizons_json, status, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, timeframe, days, max_symbols, symbol, lookback, self.db.dumps(horizons), "running", "{}"),
        )

    def _finish_run(self, run_id: str, status: str, signal_count: int, report: str, payload: dict[str, Any]) -> None:
        self.db.execute(
            """
            UPDATE backtest_runs
            SET status=?, signal_count=?, report_text=?, payload_json=?
            WHERE id=?
            """,
            (status, signal_count, report, self.db.dumps(payload), run_id),
        )

    def _save_results(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.db.executemany(
            """
            INSERT INTO backtest_results(
                run_id, strategy, symbol, signal_type, score, timeframe, open_time, price,
                future_return_pct, max_favorable_pct, max_drawdown_pct, success,
                false_positive, data_quality, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row["run_id"],
                    row["strategy"],
                    row["symbol"],
                    row["signal_type"],
                    row["score"],
                    row["timeframe"],
                    row["open_time"],
                    row["price"],
                    row["future_return_pct"],
                    row["max_favorable_pct"],
                    row["max_drawdown_pct"],
                    row["success"],
                    row["false_positive"],
                    row["data_quality"],
                    self.db.dumps(row["payload"]),
                )
                for row in rows
            ),
        )

    def _summarize_run(self, run_id: str) -> dict[str, Any]:
        rows = self.db.query("SELECT * FROM backtest_results WHERE run_id=?", (run_id,))
        by_strategy: dict[str, dict[str, Any]] = {}
        for strategy in sorted({row["strategy"] for row in rows}):
            subset = [row for row in rows if row["strategy"] == strategy]
            by_strategy[strategy] = summarize_rows(subset)
        return {
            "run_id": run_id,
            "total_results": len(rows),
            "strategies": by_strategy,
            "by_symbol": summarize_group(rows, "symbol"),
            "by_timeframe": summarize_group(rows, "timeframe"),
            "by_score_range": summarize_score_ranges(rows),
            "by_data_quality": summarize_group(rows, "data_quality"),
        }


def evaluate_signal_outcome(signal: dict[str, Any], future: list[dict[str, float]]) -> dict[str, Any]:
    price = float(signal.get("price") or 0)
    if price <= 0 or not future:
        return {
            "success": False,
            "future_return_pct": 0.0,
            "max_favorable_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "reason": "missing future candles",
        }
    final_price = float(future[-1]["close"])
    raw_return = pct(final_price, price)
    high = max(float(candle["high"]) for candle in future)
    low = min(float(candle["low"]) for candle in future)
    signal_type = str(signal.get("signal_type", "")).upper()
    if signal_type == "BUY":
        max_favorable = pct(high, price)
        max_drawdown = pct(low, price)
        success = _buy_success(signal, future, raw_return, max_favorable)
    else:
        max_favorable = pct(price, low)
        max_drawdown = -pct(high, price)
        success = raw_return <= -0.75 or max_favorable >= (2.0 if signal_type == "HIGH_RISK" else 1.5)
    return {
        "success": bool(success),
        "future_return_pct": round(raw_return, 4),
        "directional_return_pct": round(raw_return if signal_type == "BUY" else -raw_return, 4),
        "max_favorable_pct": round(max_favorable, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
        "reason": "target condition met" if success else "target condition not met",
    }


def _buy_success(signal: dict[str, Any], future: list[dict[str, float]], raw_return: float, max_favorable: float) -> bool:
    stop = _float(signal.get("invalidation_level") or signal.get("possible_stop_loss_zone"))
    take_profit = first_take_profit(signal)
    if stop and take_profit:
        for candle in future:
            if float(candle["low"]) <= stop:
                return False
            if float(candle["high"]) >= take_profit:
                return True
    return raw_return >= 0.75 or max_favorable >= 1.5


def baseline_signals(symbol: str, window: list[dict[str, float]], timeframe: str) -> list[dict[str, Any]]:
    snapshot = snapshot_from_window(window, timeframe)
    indicators = analyze_indicators(window)
    price = float(window[-1]["close"])
    signals: list[dict[str, Any]] = []
    if snapshot["change_4h"] >= 2 and snapshot["change_24h"] >= 0:
        signals.append(make_baseline_signal("momentum_baseline", symbol, "BUY", 70, price, "positive 4h momentum"))
    elif snapshot["change_4h"] <= -2:
        signals.append(make_baseline_signal("momentum_baseline", symbol, "SELL", 70, price, "negative 4h momentum"))
    relative_volume = float(indicators.get("relative_volume") or 1)
    if relative_volume >= 2.5 and snapshot["change_24h"] >= 8:
        signals.append(make_baseline_signal("volume_spike_baseline", symbol, "HIGH_RISK", 68, price, "large volume spike after strong move"))
    elif relative_volume >= 1.8:
        signal_type = "BUY" if snapshot["change_1h"] >= 0 else "SELL"
        signals.append(make_baseline_signal("volume_spike_baseline", symbol, signal_type, 68, price, "relative volume spike"))
    bucket = int(hashlib.sha256(f"{symbol}:{window[-1]['open_time']}".encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 6:
        signal_type = ("BUY", "SELL", "HIGH_RISK")[bucket % 3]
        signals.append(make_baseline_signal("random_baseline", symbol, signal_type, 50, price, "deterministic random baseline"))
    return signals


def make_baseline_signal(strategy: str, symbol: str, signal_type: str, score: int, price: float, reason: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "symbol": symbol,
        "signal_type": signal_type,
        "score": score,
        "price": price,
        "main_reason": reason,
        "possible_take_profit_zones": [round(price * 1.015, 8), round(price * 1.03, 8)],
        "possible_stop_loss_zone": round(price * 0.985, 8),
        "invalidation_level": round(price * 0.985, 8),
    }


def snapshot_from_window(window: list[dict[str, float]], timeframe: str) -> dict[str, Any]:
    price = float(window[-1]["close"])
    return {
        "symbol": "",
        "price": price,
        "change_1h": change_for_horizon(window, timeframe, "1h"),
        "change_4h": change_for_horizon(window, timeframe, "4h"),
        "change_24h": change_for_horizon(window, timeframe, "24h"),
        "volume_usdt": price * float(window[-1].get("volume", 0)),
    }


def context_at(
    symbol: str,
    candles_by_symbol: dict[str, list[dict[str, float]]],
    open_time: int,
    timeframe: str,
    lookback: int,
) -> dict[str, Any]:
    candles = candles_by_symbol.get(symbol)
    if not candles:
        return {}
    before = [candle for candle in candles if int(candle["open_time"]) <= int(open_time)]
    if len(before) < max(30, lookback):
        return {}
    return snapshot_from_window(before[-lookback:], timeframe)


def change_for_horizon(window: list[dict[str, float]], timeframe: str, horizon: str) -> float:
    offset = horizon_to_candles(horizon, timeframe)
    if len(window) <= offset:
        return 0.0
    return pct(float(window[-1]["close"]), float(window[-1 - offset]["close"]))


def horizon_to_candles(horizon: str, timeframe: str) -> int:
    return max(1, round(duration_minutes(horizon) / duration_minutes(timeframe)))


def duration_minutes(value: str) -> int:
    text = value.strip().lower()
    number = int(text[:-1])
    unit = text[-1]
    if unit == "m":
        return number
    if unit == "h":
        return number * 60
    if unit == "d":
        return number * 1440
    raise ValueError(f"Unsupported duration: {value}")


def first_take_profit(signal: dict[str, Any]) -> float | None:
    zones = signal.get("possible_take_profit_zones")
    if isinstance(zones, list) and zones:
        return _float(zones[0])
    return None


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "success_rate": None}
    successes = sum(int(row["success"]) for row in rows)
    false_positives = sum(int(row["false_positive"]) for row in rows)
    payloads = [row_payload(row) for row in rows]
    directional = [float(payload.get("outcome", {}).get("directional_return_pct", 0)) for payload in payloads]
    return {
        "count": len(rows),
        "successes": successes,
        "success_rate": round(successes / len(rows) * 100, 2),
        "false_positive_rate": round(false_positives / len(rows) * 100, 2),
        "average_directional_return_pct": round(mean(directional), 4) if directional else 0.0,
        "average_future_return_pct": round(mean(float(row["future_return_pct"]) for row in rows), 4),
        "average_max_favorable_pct": round(mean(float(row["max_favorable_pct"]) for row in rows), 4),
        "average_max_drawdown_pct": round(mean(float(row["max_drawdown_pct"]) for row in rows), 4),
        "buy_win_rate": type_rate(rows, "BUY"),
        "sell_warning_accuracy": type_rate(rows, "SELL"),
        "high_risk_warning_accuracy": type_rate(rows, "HIGH_RISK"),
    }


def type_rate(rows: list[dict[str, Any]], signal_type: str) -> str:
    subset = [row for row in rows if row["signal_type"] == signal_type]
    if not subset:
        return "unknown"
    wins = sum(int(row["success"]) for row in subset)
    return f"{wins / len(subset) * 100:.1f}% ({wins}/{len(subset)})"


def summarize_group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for value in sorted({str(row.get(key) or "unknown") for row in rows}):
        summary = summarize_rows([row for row in rows if str(row.get(key) or "unknown") == value])
        groups.append({"name": value, **summary})
    return sorted(groups, key=lambda item: item.get("count", 0), reverse=True)[:10]


def summarize_score_ranges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = {
        "0-50": [row for row in rows if int(row["score"]) <= 50],
        "51-65": [row for row in rows if 51 <= int(row["score"]) <= 65],
        "66-80": [row for row in rows if 66 <= int(row["score"]) <= 80],
        "81-100": [row for row in rows if int(row["score"]) >= 81],
    }
    return [{"name": name, **summarize_rows(items)} for name, items in buckets.items() if items]


def format_backtest_report(summary: dict[str, Any]) -> str:
    lines = [
        "CryptoRadar Backtest Report",
        f"Run ID: {summary['run_id']}",
        f"Total evaluated signals: {summary['total_results']}",
        "",
        "Strategy comparison:",
    ]
    for strategy, stats in summary["strategies"].items():
        lines.append(
            f"- {strategy}: count={stats['count']} success={stats.get('success_rate')}% "
            f"false_positive={stats.get('false_positive_rate')}% avg_directional={stats.get('average_directional_return_pct')}%"
        )
    crypto = summary["strategies"].get("cryptoradar", {})
    if crypto:
        lines.extend(
            [
                "",
                "CryptoRadar signal quality:",
                f"- BUY win rate: {crypto.get('buy_win_rate')}",
                f"- SELL warning accuracy: {crypto.get('sell_warning_accuracy')}",
                f"- HIGH_RISK warning accuracy: {crypto.get('high_risk_warning_accuracy')}",
                f"- Average max favorable move: {crypto.get('average_max_favorable_pct')}%",
                f"- Average max drawdown: {crypto.get('average_max_drawdown_pct')}%",
            ]
        )
    lines.append("")
    lines.append("This is proof/research output only. CryptoRadar still does not trade.")
    return "\n".join(lines)


def compact_signal(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": signal.get("symbol"),
        "signal_type": signal.get("signal_type"),
        "score": signal.get("score"),
        "price": signal.get("price"),
        "main_reason": signal.get("main_reason"),
    }


def row_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return BacktestJSON.loads(row.get("payload_json"))
    except Exception:
        return {}


class BacktestJSON:
    @staticmethod
    def loads(value: str | None) -> dict[str, Any]:
        import json

        if not value:
            return {}
        data = json.loads(value)
        return data if isinstance(data, dict) else {}


def pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
