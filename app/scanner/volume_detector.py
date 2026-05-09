from __future__ import annotations


def detect_volume_spike(indicators: dict, threshold: float = 2.0) -> dict:
    ratio = float(indicators.get("relative_volume") or 1.0)
    return {
        "detected": ratio >= threshold,
        "ratio": ratio,
        "reason": f"relative volume {ratio:.2f}x" if ratio >= threshold else "",
    }
