from __future__ import annotations

import logging
from typing import Any

from app.ai.lmstudio_client import LMStudioClient
from app.ai.ollama_client import OllamaClient
from app.ai.prompt_templates import FINAL_NOTE, build_signal_prompt, safe_ai_text


log = logging.getLogger(__name__)
AI_SIGNAL_TYPES = {"BUY", "SELL", "HIGH_RISK"}


class LocalAISignalAnalyzer:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        ai_cfg = config.get("ai", {})
        self.ollama_client = OllamaClient(ai_cfg.get("base_url", "http://localhost:11434"))
        self.lmstudio_client = LMStudioClient(config)
        self._availability_checked = False
        self._available = False

    def analyze(self, context: dict[str, Any], knowledge_chunks: list[dict[str, Any]]) -> str:
        fallback = self.fallback_analysis(context, knowledge_chunks)
        if not self.config.get("ai", {}).get("enabled", True):
            return fallback
        ai_cfg = self.config.get("ai", {})
        provider = ai_cfg.get("provider", "ollama")
        if context.get("signal_type") not in AI_SIGNAL_TYPES:
            return fallback
        prompt = build_signal_prompt(context, knowledge_chunks)

        if provider == "lmstudio":
            text = self._analyze_with_lmstudio(prompt)
            return safe_ai_text(text or "", fallback)
        if provider == "ollama":
            if not self._availability_checked:
                self._available = self.ollama_client.is_available()
                self._availability_checked = True
            if not self._available:
                return fallback
            text = self.ollama_client.generate(
                model=ai_cfg.get("model", "qwen2.5:7b"),
                prompt=prompt,
                temperature=float(ai_cfg.get("temperature", 0.2)),
                max_tokens=int(ai_cfg.get("max_tokens", 700)),
            )
            return safe_ai_text(text or "", fallback)

        log.warning("Unsupported AI provider '%s'; using fallback analysis", provider)
        return fallback

    def _analyze_with_lmstudio(self, prompt: str) -> str | None:
        system_prompt = (
            "You are CryptoRadar's local AI analyst. Analyze only the supplied market data. "
            "Never trade, never guarantee profit, never suggest leverage or futures, and keep the output short."
        )
        if not self._availability_checked:
            self._available = self.lmstudio_client.is_available()
            self._availability_checked = True
        if not self._available:
            return None
        return self.lmstudio_client.chat(system_prompt, prompt)

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
