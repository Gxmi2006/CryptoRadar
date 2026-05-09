from __future__ import annotations

from app.ai.signal_analyzer import LocalAISignalAnalyzer


class MockAI(LocalAISignalAnalyzer):
    def analyze(self, context: dict, knowledge_chunks: list[dict]) -> str:
        return self.fallback_analysis(context, knowledge_chunks)
