from __future__ import annotations

from typing import Any

from app.signals.signal_engine import SignalEngine


class MarketScanner:
    """Small orchestration helper for tests and future custom scanners."""

    def __init__(self, config: dict[str, Any], db: Any):
        self.engine = SignalEngine(config, db)

    def scan_snapshot(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        candle_map: dict[str, list[dict[str, float]]],
        btc_context: dict[str, Any] | None = None,
        eth_context: dict[str, Any] | None = None,
        knowledge_chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return self.engine.analyze_symbol(
            symbol=symbol,
            snapshot=snapshot,
            candle_map=candle_map,
            btc_context=btc_context or {},
            eth_context=eth_context or {},
            knowledge_chunks=knowledge_chunks or [],
        )
