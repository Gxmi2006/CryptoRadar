from __future__ import annotations

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


def build_signal_prompt(context: dict[str, Any], knowledge_chunks: list[dict[str, Any]]) -> str:
    sources = []
    for chunk in knowledge_chunks:
        sources.append(
            {
                "file_name": chunk.get("file_name"),
                "trust_level": chunk.get("trust_level", "medium"),
                "text": chunk.get("text", "")[:900],
            }
        )
    return f"""
You are CryptoRadar, a local crypto market analysis assistant. Analyze the provided Binance Spot market data.

{SAFETY_GUIDANCE}

Use only the supplied market data and source chunks. If a source is weak, outdated, conflicts with live data, or promotes risky behavior, say so.

Market context:
{context}

Relevant knowledge chunks:
{sources}

Return exactly this field format:
{OUTPUT_FORMAT}

Final Note must be exactly:
{FINAL_NOTE}
""".strip()


def safe_ai_text(text: str, fallback: str) -> str:
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
    if any(phrase in lowered for phrase in blocked):
        return fallback
    if FINAL_NOTE not in text:
        text = text.rstrip() + "\nFinal Note:\n" + FINAL_NOTE
    return text
