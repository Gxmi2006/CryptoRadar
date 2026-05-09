from __future__ import annotations

from app.notifications.notification_service import NotificationService


def sample_signal() -> dict:
    return {
        "id": "sig-1",
        "symbol": "SOLUSDT",
        "signal_type": "BUY",
        "score": 74,
        "confidence": "Medium",
        "risk_level": "Medium",
        "main_reason": "Breakout with strong volume",
        "possible_entry_zone": "142-145",
        "invalidation_level": 138,
        "warning": "Do not chase if price pumps too far.",
    }


def test_notification_threshold_and_cooldown(config: dict, db) -> None:
    config["notifications"]["telegram_enabled"] = True
    service = NotificationService(config, db)
    signal = sample_signal()
    assert service.should_notify(signal)
    message = service.format_signal(signal)
    db.execute(
        "INSERT INTO notifications(signal_id, symbol, channel, status, message) VALUES (?, ?, ?, ?, ?)",
        (signal["id"], signal["symbol"], "telegram", "sent", message),
    )
    assert not service.should_notify(signal)


def test_hold_signals_are_filtered_by_default(config: dict, db) -> None:
    service = NotificationService(config, db)
    signal = sample_signal()
    signal["signal_type"] = "HOLD"
    signal["score"] = 80
    assert not service.should_notify(signal)


def test_thresholds_are_inclusive(config: dict, db) -> None:
    service = NotificationService(config, db)
    buy = sample_signal()
    buy["score"] = config["scanner"]["buy_score_threshold"]
    assert service.should_notify(buy)

    sell = sample_signal()
    sell["signal_type"] = "SELL"
    sell["score"] = config["scanner"]["sell_score_threshold"]
    assert service.should_notify(sell)

    risk = sample_signal()
    risk["signal_type"] = "HIGH_RISK"
    risk["score"] = config["scanner"]["high_risk_threshold"]
    assert service.should_notify(risk)
