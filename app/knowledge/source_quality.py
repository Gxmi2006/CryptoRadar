from __future__ import annotations

import hashlib
import re
from pathlib import Path


RISKY_PATTERNS = [
    re.compile(r"\b(leverage|margin|borrow|liquidation|all[- ]?in)\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\b", re.IGNORECASE),
]


def source_id_for(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def assess_source(path: Path, text: str) -> dict:
    lower = text.lower()
    warnings: list[str] = []
    if any(pattern.search(text) for pattern in RISKY_PATTERNS):
        warnings.append("Source mentions high-risk behavior such as leverage, margin, all-in sizing, or certainty.")
    if "stop" not in lower and "risk" not in lower and "invalidation" not in lower:
        warnings.append("Source has little or no explicit risk-management language.")
    if len(text) < 500:
        warnings.append("Source is short; treat as weak supporting evidence.")
    category = infer_category(lower)
    trust = "Medium trust"
    if warnings:
        trust = "Low trust"
    if path.name.lower().startswith("journal"):
        category = "Trading journal"
        trust = "Experimental"
    return {
        "id": source_id_for(path),
        "file_name": path.name,
        "source_title": path.stem,
        "author": "",
        "source_date": "",
        "category": category,
        "trust_level": trust,
        "enabled": 1,
        "notes": "; ".join(warnings),
        "performance_score": 0.0,
        "warnings": warnings,
    }


def infer_category(text: str) -> str:
    if "rsi" in text or "macd" in text or "support" in text:
        return "Technical analysis"
    if "risk" in text or "position size" in text:
        return "Risk management"
    if "psychology" in text or "fear" in text or "greed" in text:
        return "Market psychology"
    if "on-chain" in text or "wallet" in text:
        return "On-chain analysis"
    if "binance" in text:
        return "Binance documentation"
    if "journal" in text:
        return "Trading journal"
    return "Personal notes"
