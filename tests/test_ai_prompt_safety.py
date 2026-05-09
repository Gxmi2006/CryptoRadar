from __future__ import annotations

from app.ai.prompt_templates import FINAL_NOTE, build_signal_prompt, safe_ai_text
from app.ai.signal_analyzer import LocalAISignalAnalyzer


def test_fallback_analysis_contains_required_final_note(config: dict) -> None:
    analyzer = LocalAISignalAnalyzer(config)
    text = analyzer.analyze(
        {
            "symbol": "BTCUSDT",
            "signal_type": "WAIT",
            "score": 54,
            "confidence": "Low",
            "timeframe": "15m",
            "trend": "sideways",
            "risk_level": "Medium",
            "main_reason": "Setup is not confirmed",
            "relative_volume": 1.0,
            "warning": "Review manually",
        },
        [],
    )
    assert FINAL_NOTE in text
    assert "100% sure" not in text.lower()


def test_ai_safety_filter_blocks_forbidden_certainty() -> None:
    fallback = f"Final Note: {FINAL_NOTE}"
    assert safe_ai_text("This is guaranteed profit", fallback) == fallback


def test_prompt_demands_structured_output() -> None:
    prompt = build_signal_prompt({"symbol": "ETHUSDT"}, [{"file_name": "risk.md", "text": "Use stops."}])
    assert "Symbol:" in prompt
    assert "Source-Based Reasoning:" in prompt
    assert FINAL_NOTE in prompt
