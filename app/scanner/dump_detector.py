from __future__ import annotations


def detect_sudden_dump(snapshot: dict, indicators: dict, change_threshold: float = -4.0, volume_threshold: float = 1.5) -> dict:
    change = float(snapshot.get("change_1h") or snapshot.get("change_24h") or 0)
    rel_volume = float(indicators.get("relative_volume") or 1)
    detected = change <= change_threshold and rel_volume >= volume_threshold
    return {"detected": detected, "strength": abs(min(0.0, change)) * rel_volume, "reason": "sudden dump with volume" if detected else ""}
