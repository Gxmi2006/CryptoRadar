from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.collector.broad_market_collector import BroadMarketCollector
from app.binance.candle_service import CandleService
from app.binance.rest_client import BinancePublicRestClient
from app.binance.symbol_service import SymbolService
from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.vector_store import rebuild_knowledge_index
from app.learning.learning_report import LearningReport
from app.learning.paper_trade_tracker import PaperTradeTracker
from app.mock.mock_market import MockMarket
from app.notifications.notification_service import NotificationService
from app.signals.signal_engine import SignalEngine
from app.storage.market_store import MarketStore
from app.storage.signal_store import SignalStore


log = logging.getLogger(__name__)
signal_log = logging.getLogger("signals")


class CryptoRadarService:
    def __init__(self, config: dict[str, Any], db: Any, project_root: Path, mock: bool = False):
        self.config = config
        self.db = db
        self.project_root = project_root
        self.mock = mock
        self.rest = BinancePublicRestClient()
        self.symbols = SymbolService(self.rest, db, config)
        self.candles = CandleService(self.rest)
        self.mock_market = MockMarket()
        self.signal_engine = SignalEngine(config, db)
        self.notifier = NotificationService(config, db)
        self.signal_store = SignalStore(db)
        self.market_store = MarketStore(db)
        self.paper_tracker = PaperTradeTracker(db, config)
        self.knowledge = KnowledgeRetriever(config, db, project_root)
        self.collector = BroadMarketCollector(config, db, self.rest)

    async def run_forever(self) -> None:
        log.info("CryptoRadar started. Mode=%s", "mock" if self.mock else "live")
        if self.config["knowledge"].get("rebuild_on_start"):
            rebuild_knowledge_index(self.config, self.db, self.project_root)
        if self.config["notifications"].get("notify_startup"):
            self.notifier.send_text("CryptoRadar started. Monitoring public Spot market data only.")

        collector_task = None
        if self.config.get("collector", {}).get("enabled", True):
            collector_task = asyncio.create_task(self._collector_loop())

        try:
            interval = int(self.config["scanner"]["scan_interval_seconds"])
            while True:
                try:
                    signals = await self.scan_once()
                    log.info("Health check: scan complete, signals=%s", len(signals))
                except asyncio.CancelledError:
                    raise
                except KeyboardInterrupt:
                    log.info("Shutdown requested.")
                    return
                except Exception as exc:
                    log.exception("Scan failed: %s", exc)
                    if self.config["notifications"].get("notify_errors"):
                        self.notifier.send_text(f"CryptoRadar error: {type(exc).__name__}. Check logs.")
                await asyncio.sleep(interval)
        finally:
            if collector_task:
                collector_task.cancel()

    async def _collector_loop(self) -> None:
        interval = max(1, int(self.config.get("collector", {}).get("interval_minutes", 30))) * 60
        while True:
            await asyncio.sleep(interval)
            try:
                summary = await asyncio.to_thread(self.collector.collect_now)
                log.info("Broad market collection complete: %s", summary)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Broad market collection failed: %s", exc)

    async def scan_once(self) -> list[dict[str, Any]]:
        snapshots, candle_map = self._load_market_data()
        btc_context = snapshots.get("BTCUSDT", {})
        eth_context = snapshots.get("ETHUSDT", {})
        generated: list[dict[str, Any]] = []

        for symbol, snapshot in snapshots.items():
            if not candle_map.get(symbol):
                continue
            chunks = self.knowledge.retrieve_for_market(symbol, snapshot, candle_map[symbol])
            signal = self.signal_engine.analyze_symbol(
                symbol=symbol,
                snapshot=snapshot,
                candle_map=candle_map[symbol],
                btc_context=btc_context,
                eth_context=eth_context,
                knowledge_chunks=chunks,
            )
            if signal:
                self.signal_store.save(signal)
                self.paper_tracker.create_for_signal(signal)
                generated.append(signal)
                signal_log.info("%s %s score=%s reason=%s", signal["signal_type"], symbol, signal["score"], signal["main_reason"])
                self.notifier.notify_signal(signal)

        self.paper_tracker.refresh_open_trades(snapshots)
        self.db.execute(
            "INSERT INTO scanner_health(status, message) VALUES (?, ?)",
            ("ok", f"scan complete, signals={len(generated)}"),
        )
        return sorted(generated, key=lambda item: item["score"], reverse=True)

    def _load_market_data(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list[dict[str, float]]]]]:
        if self.mock:
            snapshots = self.mock_market.snapshots()
            candle_map = {symbol: self.mock_market.candles(symbol) for symbol in snapshots}
            self.market_store.save_snapshots(snapshots.values())
            return snapshots, candle_map

        symbols = self.symbols.discover_symbols()
        selected = self.symbols.select_symbols(symbols)
        snapshots = self.symbols.market_snapshots(selected)
        candle_map: dict[str, dict[str, list[dict[str, float]]]] = {}
        for symbol in snapshots:
            candle_map[symbol] = self.candles.get_multi_timeframe(
                symbol,
                self.config["scanner"].get("timeframes", ["15m", "1h"]),
                limit=220,
            )
        self.market_store.save_snapshots(snapshots.values())
        return snapshots, candle_map

    def build_daily_summary(self) -> str:
        rows = self.db.query(
            """
            SELECT symbol, signal_type, score, risk_level, main_reason, created_at
            FROM signals
            WHERE datetime(created_at) >= datetime('now', '-1 day')
            ORDER BY score DESC
            LIMIT 20
            """
        )
        btc = self.db.query_one("SELECT * FROM market_snapshots WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 1")
        eth = self.db.query_one("SELECT * FROM market_snapshots WHERE symbol='ETHUSDT' ORDER BY id DESC LIMIT 1")
        lines = [
            "CryptoRadar Daily Summary",
            f"Generated at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"BTC trend: {self._trend_line(btc)}",
            f"ETH trend: {self._trend_line(eth)}",
            f"Signals generated today: {len(rows)}",
            "",
            "Top signals:",
        ]
        for row in rows[:10]:
            lines.append(f"- {row['signal_type']} {row['symbol']} score={row['score']} risk={row['risk_level']} - {row['main_reason']}")
        lines.append("")
        lines.append("Learning notes:")
        lines.append(LearningReport(self.db, self.config).short_summary())
        lines.append("This is an analysis summary, not guaranteed profit. Decide manually.")
        return "\n".join(lines)

    @staticmethod
    def _trend_line(row: dict[str, Any] | None) -> str:
        if not row:
            return "unknown"
        change = float(row.get("change_24h") or 0)
        if change > 2:
            return f"bullish ({change:.2f}% 24h)"
        if change < -2:
            return f"bearish ({change:.2f}% 24h)"
        return f"sideways ({change:.2f}% 24h)"

    def top_signals(self) -> list[dict[str, Any]]:
        return self.db.query(
            """
            SELECT symbol, signal_type, score, risk_level, main_reason, created_at
            FROM signals
            ORDER BY datetime(created_at) DESC, score DESC
            LIMIT 20
            """
        )
