from __future__ import annotations

from app.scanner.scoring import ScoringEngine


class BuySignalEngine:
    def __init__(self, scoring: ScoringEngine):
        self.scoring = scoring

    def score(self, features: dict) -> tuple[int, list[str]]:
        return self.scoring.buy_score(features)
