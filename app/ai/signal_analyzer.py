from __future__ import annotations

from typing import Any

from app.ai.ollama_client import OllamaClient
from app.ai.prompt_templates import FINAL_NOTE, build_signal_prompt, safe_ai_text


class LocalAISignalAnalyzer:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        ai_cfg = config.get("ai", {})
        self.client = OllamaClient(ai_cfg.get("base_url", "http://localhost:11434"))
        self._availability_checked = False
        self._available = False

    def analyze(self, context: dict[str, Any], knowledge_chunks: list[dict[str, Any]]) -> str:
        fallback = self.fallback_analysis(context, knowledge_chunks)
        if not self.config.get("ai", {}).get("enabled", True):
            return fallback
        ai_cfg = self.config.get("ai", {})
        if ai_cfg.get("provider", "ollama") == "ollama":
            if not self._availability_checked:
                self._available = self.client.is_available()
                self._availability_checked = True
            if not self._available:
                return fallback
        prompt = build_signal_prompt(context, knowledge_chunks)
        text = self.client.generate(
            model=ai_cfg.get("model", "qwen2.5:7b"),
            prompt=prompt,
            temperature=float(ai_cfg.get("temperature", 0.2)),
            max_tokens=int(ai_cfg.get("max_tokens", 700)),
        )
        return safe_ai_text(text or "", fallback)

    @staticmethod
    def fallback_analysis(context: dict[str, Any], knowledge_chunks: list[dict[str, Any]]) -> str:
        source_names = sorted({chunk.get("file_name", "unknown") for chunk in knowledge_chunks})
        source_reasoning = "No local knowledge chunks matched." if not source_names else "Matched: " + ", ".join(source_names)
        return "\n".join(
            [
                f"Symbol: {context.get('symbol')}",
                f"Signal: {context.get('signal_type')}",
                f"Score: {context.get('score')}",
                f"Confidence: {context.get('confidence')}",
                f"Timeframe: {context.get('timeframe')}",
                f"Trend: {context.get('trend')}",
                f"Volume: relative volume {context.get('relative_volume', 1):.2f}x",
                f"Risk Level: {context.get('risk_level')}",
                f"Main Reason: {context.get('main_reason')}",
                f"Indicator Support: RSI {context.get('rsi')}, MACD histogram {context.get('macd_histogram')}",
                f"Source-Based Reasoning: {source_reasoning}",
                "Historical Performance Note: Adaptive scoring is used when enough similar signals exist.",
                f"Invalidation Level: {context.get('invalidation_level')}",
                f"Possible Entry Zone: {context.get('possible_entry_zone')}",
                f"Possible Take-Profit Zones: {context.get('possible_take_profit_zones')}",
                f"Possible Stop-Loss Zone: {context.get('possible_stop_loss_zone')}",
                f"Warning: {context.get('warning')}",
                f"Final Note: {FINAL_NOTE}",
            ]
        )
