from __future__ import annotations

from app.scanner.scoring import ScoringEngine


class RiskEngine:
    def __init__(self, scoring: ScoringEngine):
        self.scoring = scoring

    def score_high_risk(self, features: dict) -> tuple[int, list[str]]:
        return self.scoring.high_risk_score(features)
