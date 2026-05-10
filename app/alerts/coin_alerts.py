from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.binance.alpha_client import BinanceAlphaClient
from app.binance.candle_service import CandleService
from app.binance.rest_client import BinancePublicRestClient
from app.indicators.indicators import analyze_indicators
from app.learning.ml_model import FutureMLModel
from app.notifications.notification_service import NotificationService
from app.storage.user_lists import UserListStore


class CoinAlertService:
    """Focused movement alerts for one user-selected Binance Spot coin."""

    def __init__(
        self,
        config: dict[str, Any],
        db: Any,
        rest: Any | None = None,
        notifier: NotificationService | None = None,
        alpha: Any | None = None,
    ):
        self.config = config
        self.db = db
        self.rest = rest or BinancePublicRestClient()
        self.alpha = alpha or BinanceAlphaClient()
        self.candles = CandleService(self.rest)
        self.notifier = notifier or NotificationService(config, db)
        self.ml = FutureMLModel(db, config)

    def check_coin(self, coin_id: str, force: bool = False, respect_cooldown: bool = False, preferred: bool = False) -> dict[str, Any]:
        market = self.resolve_market(coin_id)
        symbol = market["symbol"]
        alert = self.build_alert(market, preferred=preferred)
        should_send = bool(alert["events"]) or force
        if should_send and respect_cooldown and self._in_cooldown(symbol):
            alert["sent"] = False
            alert["skipped_reason"] = "cooldown"
            return alert
        if should_send:
            message = format_coin_alert(alert)
            alert["message"] = message
            alert["sent"] = self.notifier.send_text(message, signal={"id": alert["id"], "symbol": symbol})
        else:
            alert["sent"] = False
            alert["message"] = format_coin_alert(alert)
        return alert

    def check_watchlist(self, force: bool = False) -> list[dict[str, Any]]:
        symbols = list(dict.fromkeys(self.config.get("binance", {}).get("watchlist_symbols", [])))
        return [self.check_coin(symbol, force=force, respect_cooldown=True) for symbol in symbols]

    def check_preferred(self, force: bool = False) -> list[dict[str, Any]]:
        rows = UserListStore(self.db).preferred()
        return [self.check_coin(row["symbol"], force=force, respect_cooldown=True, preferred=True) for row in rows]

    def resolve_symbol(self, coin_id: str) -> str:
        return self.resolve_market(coin_id)["symbol"]

    def resolve_market(self, coin_id: str) -> dict[str, Any]:
        cleaned = normalize_coin_id(coin_id)
        if not cleaned:
            raise ValueError("Coin id is required.")
        info = self.rest.get_exchange_info()
        active = {
            item.get("symbol", "").upper()
            for item in info.get("symbols", [])
            if item.get("status") == "TRADING" and item.get("isSpotTradingAllowed") is not False
        }
        if cleaned in active:
            return {"source": "spot", "symbol": cleaned, "display_symbol": cleaned}
        quote = str(self.config.get("coin_alerts", {}).get("default_quote", "USDT")).upper()
        candidate = f"{cleaned}{quote}"
        if candidate in active:
            return {"source": "spot", "symbol": candidate, "display_symbol": candidate}
        token = self.alpha.resolve_token(cleaned)
        if token:
            trade_symbol = str(token.get("tradeSymbol") or "")
            display = f"{token.get('symbol', cleaned)} ({trade_symbol})"
            return {"source": "alpha", "symbol": trade_symbol, "display_symbol": display, "token": token}
        raise ValueError(f"No active Binance Spot or Binance Alpha symbol found for {coin_id}. Try SOLUSDT or an Alpha token symbol.")

    def build_alert(self, market: dict[str, Any] | str, preferred: bool = False) -> dict[str, Any]:
        if isinstance(market, str):
            market = {"source": "spot", "symbol": market, "display_symbol": market}
        source = str(market.get("source", "spot"))
        symbol = str(market["symbol"])
        cfg = preferred_alert_config(self.config.get("coin_alerts", {})) if preferred else self.config.get("coin_alerts", {})
        ticker = self._alpha_ticker(symbol) if source == "alpha" else self._ticker(symbol)
        candles = self._alpha_candles(symbol) if source == "alpha" else self._safe_candles(symbol)
        indicators = analyze_indicators(candles) if len(candles) >= 30 else {}
        price = _float(ticker.get("lastPrice")) or (float(candles[-1]["close"]) if candles else 0.0)
        high_24h = _float(ticker.get("highPrice"))
        low_24h = _float(ticker.get("lowPrice"))
        change_24h = _float(ticker.get("priceChangePercent"))
        change_1h = change_from_candles(candles, 4)
        change_4h = change_from_candles(candles, 16)
        relative_volume = float(indicators.get("relative_volume") or 1.0)
        rsi = indicators.get("rsi")
        events = detect_coin_events(
            price=price,
            high_24h=high_24h,
            low_24h=low_24h,
            change_24h=change_24h,
            change_1h=change_1h,
            change_4h=change_4h,
            relative_volume=relative_volume,
            rsi=rsi,
            cfg=cfg,
        )
        alert = {
            "id": f"coin-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{symbol}",
            "symbol": symbol,
            "display_symbol": market.get("display_symbol", symbol),
            "source": source,
            "priority": "P2" if preferred else "P4",
            "price": price,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "change_1h": change_1h,
            "change_4h": change_4h,
            "change_24h": change_24h,
            "volume_usdt": _float(ticker.get("quoteVolume")),
            "relative_volume": relative_volume,
            "rsi": rsi,
            "events": events,
            "token": market.get("token", {}),
            "preferred": preferred,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        prediction = self._ml_prediction(alert, indicators)
        if prediction:
            alert["ml_prediction"] = prediction
            threshold = float(self.config.get("news", {}).get("ml_breakout_probability_threshold", 0.65))
            if float(prediction.get("success_probability", 0)) >= threshold:
                events.append(
                    {
                        "type": "ML_BREAKOUT",
                        "text": f"ML filter sees {float(prediction['success_probability']) * 100:.0f}% success probability.",
                    }
                )
        return alert

    def _ticker(self, symbol: str) -> dict[str, Any]:
        tickers = self.rest.get_24hr_tickers()
        for ticker in tickers:
            if str(ticker.get("symbol", "")).upper() == symbol:
                return ticker
        raise ValueError(f"No 24h ticker found for {symbol}.")

    def _safe_candles(self, symbol: str) -> list[dict[str, float]]:
        cfg = self.config.get("coin_alerts", {})
        try:
            return self.candles.get_candles(
                symbol,
                str(cfg.get("candle_interval", "15m")),
                limit=int(cfg.get("candle_limit", 96)),
            )
        except Exception:
            return []

    def _alpha_ticker(self, symbol: str) -> dict[str, Any]:
        return self.alpha.get_ticker(symbol)

    def _alpha_candles(self, symbol: str) -> list[dict[str, float]]:
        cfg = self.config.get("coin_alerts", {})
        try:
            return self.alpha.get_klines(
                symbol,
                str(cfg.get("candle_interval", "15m")),
                limit=int(cfg.get("candle_limit", 96)),
            )
        except Exception:
            return []

    def _in_cooldown(self, symbol: str) -> bool:
        cooldown = int(self.config.get("coin_alerts", {}).get("cooldown_minutes", 30))
        row = self.db.query_one(
            """
            SELECT created_at FROM notifications
            WHERE symbol=? AND status='sent' AND message LIKE '%COIN ALERT%'
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (symbol,),
        )
        if not row:
            return False
        last = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last < timedelta(minutes=cooldown)

    def _ml_prediction(self, alert: dict[str, Any], indicators: dict[str, Any]) -> dict[str, Any] | None:
        signal_type = "BUY"
        if float(alert.get("change_24h") or 0) < -2 or any(event.get("type") in {"DUMP", "FAST_MOVE_DOWN"} for event in alert.get("events", [])):
            signal_type = "HIGH_RISK"
        score = event_score(alert.get("events", []), alert.get("change_24h"), alert.get("relative_volume"))
        signal = {
            "id": alert["id"],
            "symbol": alert["symbol"],
            "signal_type": signal_type,
            "score": score,
            "price": alert.get("price"),
            "confidence": "Medium",
            "risk_level": "High" if signal_type == "HIGH_RISK" else "Medium",
            "timeframe": self.config.get("coin_alerts", {}).get("candle_interval", "15m"),
            "main_reason": "; ".join(event.get("type", "watch") for event in alert.get("events", [])) or "preferred coin monitoring",
            "indicators": {
                **indicators,
                "rsi": alert.get("rsi"),
                "relative_volume": alert.get("relative_volume"),
            },
            "features": {
                "volume_usdt": alert.get("volume_usdt"),
                "change_1h": alert.get("change_1h"),
                "change_4h": alert.get("change_4h"),
                "change_24h": alert.get("change_24h"),
            },
            "score_details": {"buy_score": score if signal_type == "BUY" else 0, "high_risk_score": score if signal_type == "HIGH_RISK" else 0},
        }
        try:
            return self.ml.predict_for_signal(signal)
        except Exception:
            return None


def detect_coin_events(
    *,
    price: float,
    high_24h: float,
    low_24h: float,
    change_24h: float,
    change_1h: float,
    change_4h: float,
    relative_volume: float,
    rsi: Any,
    cfg: dict[str, Any],
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if change_24h >= float(cfg.get("surge_24h_pct", 10)):
        events.append({"type": "SURGE", "text": f"Price is up {change_24h:.2f}% in 24h."})
    if change_24h <= float(cfg.get("dump_24h_pct", -8)):
        events.append({"type": "DUMP", "text": f"Price is down {change_24h:.2f}% in 24h."})
    if change_1h >= float(cfg.get("surge_1h_pct", 4)):
        events.append({"type": "FAST_MOVE_UP", "text": f"Price is up {change_1h:.2f}% in about 1h."})
    if change_1h <= float(cfg.get("dump_1h_pct", -4)):
        events.append({"type": "FAST_MOVE_DOWN", "text": f"Price is down {change_1h:.2f}% in about 1h."})
    if relative_volume >= float(cfg.get("volume_spike_ratio", 2.0)):
        events.append({"type": "VOLUME_SPIKE", "text": f"Relative volume is {relative_volume:.2f}x normal."})
    near_high_pct = float(cfg.get("near_high_pct", 2.0))
    if high_24h > 0 and price >= high_24h * (1 - near_high_pct / 100) and change_24h > 0:
        events.append({"type": "NEAR_24H_HIGH", "text": f"Price is within {near_high_pct:.1f}% of the 24h high."})
    if low_24h > 0 and price <= low_24h * (1 + near_high_pct / 100) and change_24h < 0:
        events.append({"type": "NEAR_24H_LOW", "text": f"Price is within {near_high_pct:.1f}% of the 24h low."})
    rsi_value = _float(rsi)
    if change_24h >= float(cfg.get("high_risk_pump_pct", 20)) or (rsi_value >= 78 and relative_volume >= 1.5):
        events.append({"type": "HIGH_RISK_PUMP", "text": "Move may be extended; chasing can be risky."})
    if not events and abs(change_4h) >= 3:
        direction = "up" if change_4h > 0 else "down"
        events.append({"type": "WATCH", "text": f"Price is moving {direction} {change_4h:.2f}% over about 4h."})
    return events


def event_score(events: list[dict[str, str]], change_24h: Any, relative_volume: Any) -> int:
    score = 50
    event_types = {event.get("type") for event in events}
    if "SURGE" in event_types or "DUMP" in event_types:
        score += 15
    if "FAST_MOVE_UP" in event_types or "FAST_MOVE_DOWN" in event_types:
        score += 10
    if "VOLUME_SPIKE" in event_types:
        score += 10
    if "HIGH_RISK_PUMP" in event_types:
        score += 10
    score += min(abs(_float(change_24h)), 20) // 2
    if _float(relative_volume, 1) >= 1.5:
        score += 5
    return int(max(0, min(100, score)))


def preferred_alert_config(cfg: dict[str, Any]) -> dict[str, Any]:
    tuned = dict(cfg)
    tuned["surge_24h_pct"] = min(float(cfg.get("surge_24h_pct", 10)), 6)
    tuned["dump_24h_pct"] = max(float(cfg.get("dump_24h_pct", -8)), -4)
    tuned["surge_1h_pct"] = min(float(cfg.get("surge_1h_pct", 4)), 2)
    tuned["dump_1h_pct"] = max(float(cfg.get("dump_1h_pct", -4)), -2)
    tuned["volume_spike_ratio"] = min(float(cfg.get("volume_spike_ratio", 2.0)), 1.5)
    return tuned


def format_coin_alert(alert: dict[str, Any]) -> str:
    events = alert.get("events") or []
    title_type = events[0]["type"] if events else "STATUS"
    headline_emoji = event_emoji(title_type, alert)
    lines = [
        f"{headline_emoji} COIN ALERT - {alert.get('display_symbol') or alert['symbol']}",
        f"Source: Binance {str(alert.get('source', 'spot')).upper()}",
        f"Type: {event_emoji(title_type, alert)} {title_type}",
        f"Price: {format_price(alert.get('price'))}",
        f"Trend: {trend_emoji(alert)} {trend_text(alert)}",
        f"24h Change: {change_emoji(alert.get('change_24h'))} {format_pct(alert.get('change_24h'))}",
        f"1h Change: {change_emoji(alert.get('change_1h'))} {format_pct(alert.get('change_1h'))}",
        f"4h Change: {change_emoji(alert.get('change_4h'))} {format_pct(alert.get('change_4h'))}",
        f"Volume: {volume_emoji(alert)} {format_usdt(alert.get('volume_usdt'))}",
        f"Relative Volume: {volume_emoji(alert)} {float(alert.get('relative_volume') or 1):.2f}x",
    ]
    if alert.get("rsi") is not None:
        lines.append(f"RSI: {float(alert['rsi']):.1f}")
    lines.extend(["", "🧠 ML breakout:", ml_breakout_note(alert)])
    lines.extend(["", "What happened:"])
    if events:
        lines.extend(f"- {event_emoji(event['type'], alert)} {event['type']}: {event['text']}" for event in events)
    else:
        lines.append("- No major movement trigger is active right now.")
    lines.extend(
        [
            "",
            "Risk note:",
            f"{risk_emoji(events)} {risk_note(events)}",
            "",
            "Final:",
            "This is an analysis-based alert, not guaranteed profit. Decide manually.",
        ]
    )
    return "\n".join(lines)


def event_emoji(event_type: str, alert: dict[str, Any] | None = None) -> str:
    mapping = {
        "SURGE": "🚀",
        "FAST_MOVE_UP": "📈",
        "DUMP": "📉",
        "FAST_MOVE_DOWN": "📉",
        "VOLUME_SPIKE": "🔥",
        "HIGH_RISK_PUMP": "⚠️",
        "ML_BREAKOUT": "🧠",
        "NEAR_24H_HIGH": "📈",
        "NEAR_24H_LOW": "📉",
        "WATCH": "👀",
        "STATUS": "📌",
    }
    if event_type == "STATUS" and alert:
        return trend_emoji(alert)
    return mapping.get(event_type, "📌")


def trend_emoji(alert: dict[str, Any]) -> str:
    change = _float(alert.get("change_24h"))
    if change >= 10:
        return "🚀"
    if change >= 2:
        return "📈"
    if change <= -2:
        return "📉"
    return "➡️"


def change_emoji(value: Any) -> str:
    number = _float(value)
    if number >= 10:
        return "🚀"
    if number >= 0.5:
        return "📈"
    if number <= -0.5:
        return "📉"
    return "➡️"


def volume_emoji(alert: dict[str, Any]) -> str:
    return "🔥" if _float(alert.get("relative_volume"), 1) >= 1.5 else "🔊"


def risk_emoji(events: list[dict[str, str]]) -> str:
    return "⚠️" if any(event.get("type") in {"HIGH_RISK_PUMP", "DUMP", "FAST_MOVE_DOWN"} for event in events) else "🛡️"


def trend_text(alert: dict[str, Any]) -> str:
    change = _float(alert.get("change_24h"))
    if change >= 10:
        return "huge surge"
    if change >= 2:
        return "uptrend"
    if change <= -8:
        return "heavy downtrend"
    if change <= -2:
        return "downtrend"
    return "neutral"


def ml_breakout_note(alert: dict[str, Any]) -> str:
    prediction = alert.get("ml_prediction")
    if not isinstance(prediction, dict) or "success_probability" not in prediction:
        return "collecting enough labeled examples"
    return (
        f"{float(prediction['success_probability']) * 100:.0f}% success probability, "
        f"risk {float(prediction.get('risk_score', 0.5)) * 100:.0f}%, "
        f"confidence {float(prediction.get('confidence_score', 0.5)) * 100:.0f}%, "
        f"data {prediction.get('data_quality', 'unknown')}"
    )


def risk_note(events: list[dict[str, str]]) -> str:
    event_types = {event["type"] for event in events}
    if "HIGH_RISK_PUMP" in event_types:
        return "The move may already be crowded. Avoid chasing without reviewing the chart."
    if "DUMP" in event_types or "FAST_MOVE_DOWN" in event_types:
        return "Downside momentum is active. Review support and avoid emotional entries."
    if "SURGE" in event_types or "FAST_MOVE_UP" in event_types:
        return "Strong upside move detected. Waiting for a pullback may reduce chase risk."
    if "NEAR_24H_HIGH" in event_types:
        return "Price is close to the 24h high. Watch for either breakout continuation or rejection."
    if "NEAR_24H_LOW" in event_types:
        return "Price is close to the 24h low. Bounce attempts can fail if sell pressure continues."
    return "No major trigger is active; keep watching instead of forcing a decision."


def normalize_coin_id(value: str) -> str:
    return value.strip().upper().replace("/", "").replace("-", "").replace(" ", "")


def change_from_candles(candles: list[dict[str, float]], offset: int) -> float:
    if len(candles) <= offset:
        return 0.0
    current = float(candles[-1]["close"])
    previous = float(candles[-1 - offset]["close"])
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def format_price(value: Any) -> str:
    price = _float(value)
    if price >= 100:
        return f"{price:.2f}"
    if price >= 1:
        return f"{price:.4f}"
    return f"{price:.8f}"


def format_pct(value: Any) -> str:
    number = _float(value)
    return f"{number:+.2f}%"


def format_usdt(value: Any) -> str:
    number = _float(value)
    if number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    if number >= 1_000:
        return f"${number / 1_000:.2f}K"
    return f"${number:.2f}"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
