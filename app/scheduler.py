from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.ai.lmstudio_client import LMStudioClient
from app.ai.ollama_client import OllamaClient
from app.alerts.coin_alerts import CoinAlertService
from app.alerts.holdings_monitor import HoldingsMonitor
from app.backtest.backtester import BacktestEngine
from app.collector.broad_market_collector import BroadMarketCollector
from app.binance.candle_service import CandleService
from app.binance.rest_client import BinancePublicRestClient
from app.binance.symbol_service import SymbolService
from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.vector_store import rebuild_knowledge_index
from app.learning.learning_report import LearningReport
from app.learning.ml_model import FutureMLModel
from app.learning.paper_trade_tracker import PaperTradeTracker
from app.mock.mock_market import MockMarket
from app.news.preferred_news import PreferredNewsService
from app.notifications.notification_service import NotificationService
from app.signals.signal_engine import SignalEngine
from app.storage.market_store import MarketStore
from app.storage.signal_store import SignalStore
from app.storage.user_lists import UserListStore
from app.telegram_bot.command_bot import TelegramCommandBot


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
        self.ml = FutureMLModel(db, config, project_root)
        self.coin_alerts = CoinAlertService(config, db, self.rest, self.notifier)
        self.news = PreferredNewsService(config, db, self.coin_alerts, self.notifier)
        self.holdings_monitor = HoldingsMonitor(config, db, self.coin_alerts, self.notifier)
        self.user_lists = UserListStore(db)
        self.telegram_bot = TelegramCommandBot(config, db, self)
        self.paused = False
        self.service_started_at = datetime.now(timezone.utc)

    async def run_forever(self) -> None:
        self._startup()

        collector_task = None
        if self.config.get("collector", {}).get("enabled", True):
            collector_task = asyncio.create_task(self._collector_loop())

        try:
            await self._scanner_loop()
        finally:
            if collector_task:
                collector_task.cancel()

    async def run_auto_pipeline(self, run_once: bool = False, status: Callable[[str], None] | None = None) -> None:
        status = status or print
        automation = self.config.get("automation", {})
        if not automation.get("enabled", True):
            status("Automation is disabled in config.")
            return

        self._startup(status)
        status("CryptoRadar auto pipeline is running. Press Ctrl+C to stop.")

        if run_once:
            if automation.get("collect_market_data", True):
                await self._run_collector_once(status)
            if automation.get("scan_market", True):
                await self._run_scan_once(status)
            if self._watchlist_alerts_enabled():
                await self._run_watchlist_alerts_once(status)
            if self.config.get("coin_alerts", {}).get("preferred_auto_alerts", True):
                await self._run_preferred_alerts_once(status)
            if self._preferred_news_enabled():
                await self._run_preferred_news_once(status)
            await asyncio.to_thread(self.holdings_monitor.check_holdings)
            if automation.get("auto_train_ml", True):
                await self._run_ml_training_once(status)
            await self._run_learning_report_once(status)
            self._print_pipeline_status(status)
            return

        tasks: list[asyncio.Task] = []
        if automation.get("scan_market", True):
            tasks.append(asyncio.create_task(self._scanner_loop(status=status)))
        if automation.get("collect_market_data", True) and self.config.get("collector", {}).get("enabled", True):
            tasks.append(asyncio.create_task(self._collector_loop(status=status, run_immediately=True)))
        if automation.get("auto_train_ml", True):
            tasks.append(asyncio.create_task(self._ml_training_loop(status=status, run_immediately=True)))
        if self._watchlist_alerts_enabled():
            tasks.append(asyncio.create_task(self._watchlist_alert_loop(status=status)))
        if self.config.get("coin_alerts", {}).get("preferred_auto_alerts", True):
            tasks.append(asyncio.create_task(self._preferred_alert_loop(status=status)))
        if self._preferred_news_enabled():
            tasks.append(asyncio.create_task(self._preferred_news_loop(status=status)))
        if self.config.get("backtest", {}).get("auto_run", True):
            tasks.append(asyncio.create_task(self._backtest_loop(status=status)))
        tasks.append(asyncio.create_task(self._holdings_loop(status=status)))
        tasks.append(asyncio.create_task(self.telegram_bot.run_forever(status=status)))
        tasks.append(asyncio.create_task(self._health_loop(status=status)))
        tasks.append(asyncio.create_task(self._learning_report_loop(status=status)))
        tasks.append(asyncio.create_task(self._status_loop(status=status)))

        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()

    def _startup(self, status: Callable[[str], None] | None = None) -> None:
        message = f"CryptoRadar started. Mode={'mock' if self.mock else 'live'}"
        log.info(message)
        if status:
            status(message)
        if self.config["knowledge"].get("rebuild_on_start"):
            if status:
                status("Rebuilding local knowledge index...")
            rebuild_knowledge_index(self.config, self.db, self.project_root)
        if self.config["notifications"].get("notify_startup"):
            self.notifier.send_text(self.startup_text())

    async def _scanner_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = int(self.config["scanner"]["scan_interval_seconds"])
        while True:
            try:
                if self.paused:
                    if status:
                        status("Scanner paused from Telegram command.")
                else:
                    await self._run_scan_once(status)
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt:
                log.info("Shutdown requested.")
                return
            except Exception as exc:
                log.exception("Scan failed: %s", exc)
                if status:
                    status(f"Scan failed: {type(exc).__name__}. Check logs.")
                if self.config["notifications"].get("notify_errors"):
                    self.notifier.send_text(f"CryptoRadar error: {type(exc).__name__}. Check logs.")
            await asyncio.sleep(interval)

    async def _run_scan_once(self, status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        signals = await self.scan_once()
        log.info("Health check: scan complete, signals=%s", len(signals))
        if status:
            status(f"Scan complete. Signals generated: {len(signals)}")
        return signals

    async def _collector_loop(self, status: Callable[[str], None] | None = None, run_immediately: bool = False) -> None:
        interval = max(1, int(self.config.get("collector", {}).get("interval_minutes", 30))) * 60
        if run_immediately:
            await self._run_collector_once(status)
        while True:
            await asyncio.sleep(interval)
            try:
                await self._run_collector_once(status)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Broad market collection failed: %s", exc)
                if status:
                    status(f"Broad market collection failed: {type(exc).__name__}. Check logs.")

    async def _run_collector_once(self, status: Callable[[str], None] | None = None) -> dict[str, Any]:
        try:
            summary = await asyncio.to_thread(self.collector.collect_now, status)
        except Exception as exc:
            log.warning("Broad market collection failed: %s", exc)
            if status:
                status(f"Broad market collection failed: {type(exc).__name__}. Check logs.")
            return {"collected": 0, "candle_symbols": 0, "error": type(exc).__name__}
        log.info("Broad market collection complete: %s", summary)
        if status:
            status(f"Market data collected: {summary.get('collected', 0)} symbols, candles for {summary.get('candle_symbols', 0)}.")
        return summary

    async def _ml_training_loop(self, status: Callable[[str], None] | None = None, run_immediately: bool = False) -> None:
        interval = max(1, int(self.config.get("automation", {}).get("ml_train_interval_minutes", 60))) * 60
        if run_immediately:
            await self._run_ml_training_once(status)
        while True:
            await asyncio.sleep(interval)
            await self._run_ml_training_once(status)

    async def _run_ml_training_once(self, status: Callable[[str], None] | None = None) -> str:
        try:
            report = await asyncio.to_thread(self.ml.train, auto=True)
        except TypeError:
            report = await asyncio.to_thread(self.ml.train)
        except Exception as exc:
            log.warning("ML training failed: %s", exc)
            report = f"ML training failed: {type(exc).__name__}. Check logs."
        if status:
            status(f"ML training: {report}")
        log.info("ML training result: %s", report)
        return report

    async def _watchlist_alert_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(60, int(self.config.get("coin_alerts", {}).get("interval_seconds", 300)))
        while True:
            await asyncio.sleep(interval)
            await self._run_watchlist_alerts_once(status)

    async def _run_watchlist_alerts_once(self, status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        try:
            alerts = await asyncio.to_thread(self.coin_alerts.check_watchlist)
        except Exception as exc:
            log.warning("Watchlist coin alerts failed: %s", exc)
            if status:
                status(f"Watchlist coin alerts failed: {type(exc).__name__}. Check logs.")
            return []
        sent = sum(1 for alert in alerts if alert.get("sent"))
        triggered = sum(1 for alert in alerts if alert.get("events"))
        if status and alerts:
            status(f"Watchlist coin alerts checked: {len(alerts)} symbols, triggered={triggered}, sent={sent}.")
        return alerts

    async def _preferred_alert_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(60, int(self.config.get("coin_alerts", {}).get("preferred_interval_seconds", 180)))
        while True:
            await asyncio.sleep(interval)
            await self._run_preferred_alerts_once(status)

    async def _run_preferred_alerts_once(self, status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        if self.paused:
            return []
        try:
            alerts = await asyncio.to_thread(self.coin_alerts.check_preferred)
        except Exception as exc:
            log.warning("Preferred coin alerts failed: %s", exc)
            if status:
                status(f"Preferred coin alerts failed: {type(exc).__name__}. Check logs.")
            return []
        sent = sum(1 for alert in alerts if alert.get("sent"))
        triggered = sum(1 for alert in alerts if alert.get("events"))
        if status and alerts:
            status(f"Preferred coin alerts checked: {len(alerts)} symbols, triggered={triggered}, sent={sent}.")
        return alerts

    async def _holdings_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(60, int(self.config.get("coin_alerts", {}).get("preferred_interval_seconds", 180)))
        while True:
            await asyncio.sleep(interval)
            if self.paused:
                continue
            try:
                results = await asyncio.to_thread(self.holdings_monitor.check_holdings)
            except Exception as exc:
                log.warning("Holdings monitor failed: %s", exc)
                if status:
                    status(f"Holdings monitor failed: {type(exc).__name__}. Check logs.")
                continue
            sent = sum(1 for row in results if row.get("sent"))
            if status and results:
                status(f"Holdings checked: {len(results)} symbols, urgent alerts={sent}.")

    async def _preferred_news_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(5, int(self.config.get("news", {}).get("interval_minutes", 15))) * 60
        while True:
            await asyncio.sleep(interval)
            await self._run_preferred_news_once(status)

    async def _run_preferred_news_once(self, status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        if self.paused or not self._preferred_news_enabled():
            return []
        try:
            alerts = await asyncio.to_thread(self.news.check_preferred_news)
        except Exception as exc:
            log.warning("Preferred news alerts failed: %s", exc)
            if status:
                status(f"Preferred news alerts failed: {type(exc).__name__}. Check logs.")
            return []
        sent = sum(1 for alert in alerts if alert.get("sent"))
        if status and alerts:
            status(f"Preferred news checked: matched={len(alerts)}, sent={sent}.")
        return alerts

    async def _backtest_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(1, int(self.config.get("backtest", {}).get("interval_hours", 24))) * 3600
        while True:
            await asyncio.sleep(interval)
            try:
                report = await asyncio.to_thread(BacktestEngine(self.config, self.db).run)
            except Exception as exc:
                log.warning("Backtest scheduler failed: %s", exc)
                if status:
                    status(f"Backtest scheduler failed: {type(exc).__name__}. Check logs.")
                continue
            if status:
                first_line = report.splitlines()[0] if report else "Backtest finished."
                status(f"Backtest scheduler: {first_line}")

    def _watchlist_alerts_enabled(self) -> bool:
        cfg = self.config.get("coin_alerts", {})
        return bool(cfg.get("enabled", True) and cfg.get("watchlist_auto_alerts", True) and self.config.get("binance", {}).get("watchlist_symbols"))

    def _preferred_news_enabled(self) -> bool:
        return bool(self.config.get("news", {}).get("enabled", True))

    async def _health_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval = max(60, int(self.config.get("automation", {}).get("health_check_interval_seconds", 300)))
        while True:
            await asyncio.sleep(interval)
            await self._run_health_check(status)

    async def _run_health_check(self, status: Callable[[str], None] | None = None) -> dict[str, Any]:
        health = await asyncio.to_thread(self.health_snapshot)
        issues = []
        if health["binance"] != "running":
            issues.append("Binance data issue detected. Retrying...")
        if health["telegram"] != "running":
            issues.append("Telegram connection issue. Retrying...")
        if health["local_ai"] == "not connected":
            issues.append("Local AI not connected. Rule-based alerts still running.")
        if status:
            status("Health check: " + ", ".join(f"{key}={value}" for key, value in health.items()))
        for issue in issues:
            self.notifier.send_text(issue)
        self.db.execute("INSERT INTO scanner_health(status, message) VALUES (?, ?)", ("ok", self.db.dumps(health)))
        return health

    async def _learning_report_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval_minutes = int(self.config.get("automation", {}).get("learning_report_interval_minutes", 60))
        if interval_minutes <= 0:
            return
        interval = interval_minutes * 60
        while True:
            await asyncio.sleep(interval)
            await self._run_learning_report_once(status)

    async def _run_learning_report_once(self, status: Callable[[str], None] | None = None) -> str:
        try:
            report = await asyncio.to_thread(LearningReport(self.db, self.config).render_text)
        except Exception as exc:
            log.warning("Learning report failed: %s", exc)
            report = f"Learning report failed: {type(exc).__name__}. Check logs."
        if status:
            first_line = report.splitlines()[0] if report else "Learning report updated."
            status(first_line)
        return report

    async def _status_loop(self, status: Callable[[str], None] | None = None) -> None:
        interval_minutes = int(self.config.get("automation", {}).get("status_interval_minutes", 10))
        if interval_minutes <= 0:
            return
        interval = interval_minutes * 60
        while True:
            await asyncio.sleep(interval)
            self._print_pipeline_status(status)

    def _print_pipeline_status(self, status: Callable[[str], None] | None = None) -> None:
        if not status:
            return
        signals = self.db.query_one("SELECT COUNT(*) AS count FROM signals")
        broad = self.db.query_one("SELECT COUNT(*) AS count FROM broad_market_snapshots")
        examples = self.db.query_one("SELECT COUNT(*) AS count FROM ml_training_examples")
        predictions = self.db.query_one("SELECT COUNT(*) AS count FROM ml_predictions")
        status(
            "Status: "
            f"signals={int(signals['count']) if signals else 0}, "
            f"broad_snapshots={int(broad['count']) if broad else 0}, "
            f"ml_examples={int(examples['count']) if examples else 0}, "
            f"ml_predictions={int(predictions['count']) if predictions else 0}"
        )

    def health_snapshot(self) -> dict[str, Any]:
        binance_status = "running"
        try:
            self.rest.get_ticker_price("BTCUSDT")
        except Exception:
            binance_status = "issue"
        return {
            "scanner": "paused" if self.paused else "running",
            "telegram": "running" if self.notifier.telegram.configured else "not configured",
            "ml_learner": "running" if self.config.get("ml", {}).get("enabled", True) else "disabled",
            "local_ai": self._local_ai_status(),
            "binance": binance_status,
            "preferred_coins": len(self.user_lists.preferred()),
            "holdings": len(self.user_lists.holdings()),
            "signals_today": self._signals_today(),
            "last_update": datetime.now(timezone.utc).strftime("%H:%M"),
        }

    def status_text(self) -> str:
        health = self.health_snapshot()
        return "\n".join(
            [
                "CryptoRadar Status",
                f"Scanner: {health['scanner']}",
                f"Telegram: {health['telegram']}",
                f"ML learner: {health['ml_learner']}",
                f"Local AI: {health['local_ai']}",
                f"Preferred coins: {health['preferred_coins']}",
                f"Holdings: {health['holdings']}",
                f"Signals today: {health['signals_today']}",
                f"Last update: {health['last_update']}",
                "Safety: notification-only, no trading permissions.",
            ]
        )

    def startup_text(self) -> str:
        health = self.health_snapshot()
        return "\n".join(
            [
                "CryptoRadar Started",
                "Mode: Notification-only",
                f"Market scanner: {health['scanner']}",
                f"Telegram bot: {health['telegram']}",
                f"ML learner: {health['ml_learner']}",
                f"Preferred watchlist: loaded ({health['preferred_coins']})",
                f"Holdings monitor: loaded ({health['holdings']})",
                f"Local AI: {health['local_ai']}",
                "Safety: No trading permissions",
            ]
        )

    def _signals_today(self) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS count FROM signals WHERE datetime(created_at) >= datetime('now', 'start of day')"
        )
        return int(row["count"]) if row else 0

    def _local_ai_status(self) -> str:
        ai_cfg = self.config.get("ai", {})
        if not ai_cfg.get("enabled", True):
            return "disabled"
        provider = ai_cfg.get("provider", "lmstudio")
        try:
            if provider == "lmstudio":
                return "connected" if LMStudioClient(self.config).is_available() else "not connected"
            if provider == "ollama":
                return "connected" if OllamaClient(ai_cfg.get("base_url", "http://localhost:11434")).is_available() else "not connected"
        except Exception:
            return "not connected"
        return "not connected"

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
        try:
            ml_report = await asyncio.to_thread(self.ml.train, auto=True)
            if not ml_report.startswith("ML training skipped"):
                log.info("ML auto update after performance refresh: %s", ml_report)
        except Exception as exc:
            log.warning("ML auto update after performance refresh failed: %s", exc)
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
