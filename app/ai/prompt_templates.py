from __future__ import annotations

import re
from typing import Any


FINAL_NOTE = "This is an analysis-based signal, not guaranteed profit. Decide manually."


SAFETY_GUIDANCE = """
Safety rules:
- Do not promise profit or certainty.
- Do not recommend all-in sizing.
- Do not recommend leverage, derivatives, margin, borrowing, or automated execution.
- Do not invent market data or source citations.
- Use cautious phrasing such as Possible Buy, Sell Warning, Hold, Wait, Avoid, or High Risk.
- Always include risk, invalidation, and a manual-decision reminder.
""".strip()


OUTPUT_FORMAT = """
Symbol:
Signal:
Score:
Confidence:
Timeframe:
Trend:
Volume:
Risk Level:
Main Reason:
Indicator Support:
Source-Based Reasoning:
Historical Performance Note:
Invalidation Level:
Possible Entry Zone:
Possible Take-Profit Zones:
Possible Stop-Loss Zone:
Warning:
Final Note:
""".strip()


SECRET_PATTERNS = (
    re.compile(r"(?i)(telegram[_-]?bot[_-]?token|telegram[_-]?chat[_-]?id|api[_-]?key|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b"),
)


def build_signal_prompt(context: dict[str, Any], knowledge_chunks: list[dict[str, Any]]) -> str:
    sources = []
    for chunk in knowledge_chunks:
        sources.append(
            {
                "file_name": sanitize_value(chunk.get("file_name")),
                "trust_level": sanitize_value(chunk.get("trust_level", "medium")),
                "text": sanitize_value(chunk.get("text", "")[:900]),
            }
        )
    safe_context = sanitize_value(context)
    return f"""
You are CryptoRadar, a local crypto market analysis assistant. Analyze the provided Binance Spot market data.
You may reason internally, but do not include chain-of-thought. Output only the requested final fields.

{SAFETY_GUIDANCE}

Use only the supplied market data and source chunks. If a source is weak, outdated, conflicts with live data, or promotes risky behavior, say so.

Market context:
{safe_context}

Relevant knowledge chunks:
{sources}

Return exactly this field format:
{OUTPUT_FORMAT}

Final Note must be exactly:
{FINAL_NOTE}
""".strip()


def safe_ai_text(text: str, fallback: str) -> str:
    text = sanitize_value(text)
    if not text.strip():
        return fallback
    lowered = text.lower()
    blocked = [
        "100% sure",
        "go all-in",
        "buy now immediately",
        "sell now immediately",
        "guaranteed profit",
    ]
    safety_text = lowered.replace("not guaranteed profit", "")
    if any(phrase in safety_text for phrase in blocked):
        return fallback
    if FINAL_NOTE not in text:
        text = text.rstrip() + "\nFinal Note:\n" + FINAL_NOTE
    return text


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[redacted]", text)
        return text
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_value(item) for key, item in value.items()}
    return value
