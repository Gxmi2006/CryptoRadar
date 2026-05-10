from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DEFAULT_THRESHOLDS = {
    "buy_win_pct": 2.5,
    "buy_loss_pct": -1.5,
    "sell_win_pct": 2.0,
    "sell_loss_pct": -2.0,
    "high_risk_win_pct": 3.0,
    "high_risk_loss_pct": -3.0,
    "neutral_after_minutes": 240,
}


def performance_thresholds(config: dict[str, Any] | None = None) -> dict[str, float]:
    configured = ((config or {}).get("learning") or {}).get("performance_thresholds", {})
    merged = {**DEFAULT_THRESHOLDS, **configured}
    return {key: float(value) for key, value in merged.items()}


def classify_paper_result(
    *,
    signal_type: str,
    move_pct: float,
    max_profit_pct: float,
    max_drawdown_pct: float,
    take_profit_hit: bool = False,
    stop_loss_hit: bool = False,
    age_minutes: float | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    thresholds = performance_thresholds(config)
    side = signal_type.upper()
    if side == "BUY":
        if take_profit_hit or max_profit_pct >= thresholds["buy_win_pct"] or move_pct >= thresholds["buy_win_pct"]:
            return "win"
        if stop_loss_hit or max_drawdown_pct <= thresholds["buy_loss_pct"] or move_pct <= thresholds["buy_loss_pct"]:
            return "loss"
    elif side == "SELL":
        if max_profit_pct >= thresholds["sell_win_pct"] or move_pct >= thresholds["sell_win_pct"]:
            return "win"
        if max_drawdown_pct <= thresholds["sell_loss_pct"] or move_pct <= thresholds["sell_loss_pct"]:
            return "loss"
    elif side == "HIGH_RISK":
        if max_profit_pct >= thresholds["high_risk_win_pct"] or move_pct >= thresholds["high_risk_win_pct"]:
            return "win"
        if max_drawdown_pct <= thresholds["high_risk_loss_pct"] or move_pct <= thresholds["high_risk_loss_pct"]:
            return "loss"
    elif side == "HOLD":
        if age_minutes is None or age_minutes >= thresholds["neutral_after_minutes"]:
            return "neutral"
    if age_minutes is not None and age_minutes >= thresholds["neutral_after_minutes"]:
        return "neutral"
    return "unknown"


def training_result_from_performance(row: dict[str, Any], config: dict[str, Any] | None = None) -> str | None:
    existing = str(row.get("performance_result") or row.get("signal_result") or "").lower()
    if existing not in {"win", "loss", "neutral"}:
        return None
    signal_type = str(row.get("signal_type") or "").upper()
    if not signal_type:
        return existing
    derived = classify_paper_result(
        signal_type=signal_type,
        move_pct=float(row.get("max_profit_pct") or 0),
        max_profit_pct=float(row.get("max_profit_pct") or 0),
        max_drawdown_pct=float(row.get("max_drawdown_pct") or 0),
        take_profit_hit=bool(row.get("take_profit_reached")),
        stop_loss_hit=bool(row.get("stop_loss_reached")),
        age_minutes=performance_age_minutes(row.get("updated_at")),
        config=config,
    )
    if derived in {"win", "loss", "neutral"}:
        return derived
    if row.get("max_profit_pct") is not None or row.get("max_drawdown_pct") is not None:
        return "neutral"
    return existing


def performance_age_minutes(updated_at: Any) -> float | None:
    if not updated_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 60


def row_age_minutes(created_at: Any) -> float | None:
    if not created_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 60
