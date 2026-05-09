from __future__ import annotations

from typing import Any


class FutureMLModel:
    """Optional placeholder for later local ML scoring.

    Version 1 deliberately avoids fine-tuning the LLM. A future local model can
    consume saved signal features and output success probability, risk score, and
    confidence as one input among many.
    """

    def __init__(self, db: Any):
        self.db = db

    def predict(self, features: dict[str, Any]) -> dict[str, float]:
        return {"success_probability": 0.5, "risk_score": 0.5, "confidence_score": 0.5}
