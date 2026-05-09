from __future__ import annotations

from app.ai.prompt_templates import FINAL_NOTE, build_signal_prompt, safe_ai_text
from app.ai.signal_analyzer import LocalAISignalAnalyzer
from app.ai.telegram_message_formatter import TelegramMessageFormatter, build_raw_signal_data
from app.ai.lmstudio_client import LMStudioClient


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
    assert "do not include chain-of-thought" in prompt
    assert FINAL_NOTE in prompt


def test_lmstudio_chat_accepts_per_call_reasoning_overrides(config: dict) -> None:
    config["ai"]["reasoning_effort"] = "none"
    client = LMStudioClient(config)
    captured = {}

    class Message:
        content = "ok"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]

    class Completions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return Response()

    class Chat:
        completions = Completions()

    class FakeClient:
        chat = Chat()

    client._client = FakeClient()
    assert client.chat("system", "user", max_tokens=1200, reasoning_effort="medium", timeout=45) == "ok"
    assert captured["max_tokens"] == 1200
    assert captured["timeout"] == 45
    assert captured["extra_body"] == {"reasoning_effort": "medium"}


def test_lmstudio_analysis_uses_analysis_reasoning_settings(config: dict) -> None:
    config["ai"]["enabled"] = True
    config["ai"]["provider"] = "lmstudio"
    config["ai"]["analysis_reasoning_effort"] = "medium"
    config["ai"]["analysis_max_tokens"] = 1200
    config["ai"]["analysis_timeout_seconds"] = 45
    analyzer = LocalAISignalAnalyzer(config)
    captured = {}

    class FakeLMStudio:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def chat(system_prompt, user_prompt, max_tokens=None, reasoning_effort=None, timeout=None):
            captured.update(
                {
                    "system_prompt": system_prompt,
                    "max_tokens": max_tokens,
                    "reasoning_effort": reasoning_effort,
                    "timeout": timeout,
                }
            )
            return f"Symbol: SOLUSDT\nSignal: BUY\nFinal Note: {FINAL_NOTE}"

    analyzer.lmstudio_client = FakeLMStudio()
    text = analyzer.analyze(
        {
            "symbol": "SOLUSDT",
            "signal_type": "BUY",
            "score": 75,
            "confidence": "Medium",
            "timeframe": "15m",
            "trend": "uptrend",
            "risk_level": "Medium",
            "main_reason": "Breakout with volume",
            "relative_volume": 2.1,
            "warning": "Review manually",
        },
        [],
    )
    assert "Signal: BUY" in text
    assert "reason internally" in captured["system_prompt"]
    assert captured["max_tokens"] == 1200
    assert captured["reasoning_effort"] == "medium"
    assert captured["timeout"] == 45


def test_telegram_formatter_uses_fixed_template_and_whitelisted_data(config: dict) -> None:
    config["telegram_formatting"]["use_template_formatter"] = True
    signal = {
        "symbol": "SOLUSDT",
        "signal_type": "BUY",
        "score": 75,
        "confidence": "Medium",
        "risk_level": "Medium",
        "timeframe": "15m",
        "price": 142.5,
        "main_reason": "Breakout with volume",
        "invalidation_level": 137.8,
        "possible_entry_zone": "140.50-142.50",
        "possible_take_profit_zones": [146.0, 150.0],
        "indicators": {"rsi": 61.4, "macd_histogram": 0.18, "ema_alignment": "bullish", "relative_volume": 2.1},
        "features": {"trend": "uptrend", "change_24h": 4.8},
        "telegram_bot_token": "123456789:SECRET_SHOULD_NOT_LEAK",
    }
    raw = build_raw_signal_data(signal)
    assert "telegram_bot_token" not in raw
    formatted = TelegramMessageFormatter(config).format(signal)
    assert "🟢 BUY SIGNAL" in formatted
    assert "SOLUSDT" in formatted
    assert "Score: 75/100" in formatted
    assert "Entry: 140.50-142.50" in formatted
    assert FINAL_NOTE in formatted
