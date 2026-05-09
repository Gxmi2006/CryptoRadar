from __future__ import annotations

from app.scanner.scoring import ScoringEngine


class HoldSignalEngine:
    def __init__(self, scoring: ScoringEngine):
        self.scoring = scoring

    def score(self, features: dict) -> tuple[int, list[str]]:
        return self.scoring.hold_score(features)
