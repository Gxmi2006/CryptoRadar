from __future__ import annotations

from typing import Any

from app.ai.prompt_templates import FINAL_NOTE, sanitize_value


SIGNAL_LABELS = {
    "BUY": ("🟢", "BUY SIGNAL"),
    "SELL": ("🔴", "SELL WARNING"),
    "HIGH_RISK": ("⚠️", "HIGH RISK"),
    "HOLD": ("🔵", "HOLD"),
    "WAIT": ("⏳", "WAIT"),
    "AVOID": ("🚫", "AVOID"),
}


class TelegramMessageFormatter:
    """Deterministic Telegram formatter.

    This formatter uses code templates only. It does not call any AI model and
    does not rewrite or infer any market values.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.format_cfg = config.get("telegram_formatting", {})

    def format(self, signal: dict[str, Any]) -> str:
        raw = build_raw_signal_data(signal)
        signal_type = str(raw.get("signal_type", "")).upper()
        emoji, label = SIGNAL_LABELS.get(signal_type, ("📌", f"{signal_type} SIGNAL"))
        if not self.format_cfg.get("include_emojis", True):
            emoji = ""
        header = f"{emoji} {label} — {raw.get('symbol')}".strip()

        lines = [
            header,
            "",
            f"Score: {raw.get('score')}/100",
            f"Confidence: {raw.get('confidence', 'Unknown')}",
            f"Risk: {raw.get('risk_level', 'Unknown')}",
            f"Trend: {raw.get('trend', 'Unknown')}",
        ]

        details = _compact_details(raw)
        if details:
            lines.extend(["", "Market details:", *details])

        lines.extend(
            [
                "",
                "Why this matters:",
                str(raw.get("reason", "Signal conditions matched the configured rules.")),
            ]
        )

        if self.format_cfg.get("include_key_levels", True):
            lines.extend(
                [
                    "",
                    "Key levels:",
                    f"Entry: {raw.get('possible_entry_zone', 'Review manually')}",
                    f"Invalidation: {raw.get('invalidation_level', 'Review manually')}",
                    f"Take-profit: {_format_take_profit(raw.get('possible_take_profit_zone'))}",
                ]
            )

        if self.format_cfg.get("include_risk_note", True):
            lines.extend(
                [
                    "",
                    "Risk note:",
                    str(raw.get("warning", "Do not chase fast moves; review manually.")),
                ]
            )

        lines.extend(["", "Final:", FINAL_NOTE])
        message = "\n".join(lines)
        max_chars = int(self.format_cfg.get("max_message_chars", 1200))
        if len(message) > max_chars:
            message = message[: max_chars - 3].rstrip() + "..."
        return message


def build_raw_signal_data(signal: dict[str, Any]) -> dict[str, Any]:
    indicators = signal.get("indicators") or {}
    features = signal.get("features") or {}
    raw = {
        "symbol": signal.get("symbol"),
        "signal_type": signal.get("signal_type") or signal.get("type"),
        "score": signal.get("score"),
        "confidence": signal.get("confidence"),
        "risk_level": signal.get("risk_level"),
        "trend": features.get("trend") or signal.get("trend"),
        "timeframe": signal.get("timeframe"),
        "price": signal.get("price"),
        "percentage_change": features.get("change_24h"),
        "rsi": indicators.get("rsi"),
        "macd_status": _macd_status(indicators),
        "ema_structure": indicators.get("ema_alignment"),
        "volume_condition": _volume_condition(indicators),
        "btc_trend": signal.get("btc_trend"),
        "eth_trend": signal.get("eth_trend"),
        "reason": signal.get("main_reason"),
        "warning": signal.get("warning"),
        "invalidation_level": signal.get("invalidation_level"),
        "possible_entry_zone": signal.get("possible_entry_zone"),
        "possible_take_profit_zone": signal.get("possible_take_profit_zones"),
        "possible_stop_loss_zone": signal.get("possible_stop_loss_zone"),
        "source_based_reasoning": _source_note(signal),
        "historical_performance_note": "Adaptive scoring will include this signal after outcome tracking.",
    }
    return {key: sanitize_value(value) for key, value in raw.items() if value not in (None, "", [])}


def _compact_details(raw: dict[str, Any]) -> list[str]:
    details: list[str] = []
    if "price" in raw:
        details.append(f"Price: {_format_number(raw['price'])}")
    if "percentage_change" in raw:
        details.append(f"24h change: {_format_number(raw['percentage_change'])}%")
    if "timeframe" in raw:
        details.append(f"Timeframe: {raw['timeframe']}")
    if "rsi" in raw:
        details.append(f"RSI: {_format_number(raw['rsi'])}")
    if "macd_status" in raw:
        details.append(f"MACD: {raw['macd_status']}")
    if "ema_structure" in raw:
        details.append(f"EMA: {raw['ema_structure']}")
    if "volume_condition" in raw:
        details.append(f"Volume: {raw['volume_condition']}")
    if "btc_trend" in raw:
        details.append(f"BTC trend: {raw['btc_trend']}")
    if "eth_trend" in raw:
        details.append(f"ETH trend: {raw['eth_trend']}")
    return details


def _format_take_profit(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_format_number(item) for item in value)
    if value is None:
        return "Review manually"
    return str(value)


def _format_number(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:.8g}"


def _macd_status(indicators: dict[str, Any]) -> str | None:
    histogram = indicators.get("macd_histogram")
    if histogram is None:
        return None
    try:
        return "bullish" if float(histogram) > 0 else "bearish"
    except (TypeError, ValueError):
        return None


def _volume_condition(indicators: dict[str, Any]) -> str | None:
    relative_volume = indicators.get("relative_volume")
    if relative_volume is None:
        return None
    try:
        return f"relative volume {float(relative_volume):.2f}x"
    except (TypeError, ValueError):
        return None


def _source_note(signal: dict[str, Any]) -> str | None:
    sources = signal.get("knowledge_sources_used") or []
    if not sources:
        return None
    return "Matched local sources: " + ", ".join(str(source) for source in sources[:5])
