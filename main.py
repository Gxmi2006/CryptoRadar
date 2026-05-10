from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ai.lmstudio_client import LMStudioClient
from app.ai.telegram_message_formatter import TelegramMessageFormatter
from app.collector.broad_market_collector import BroadMarketCollector
from app.config import load_config, safe_config_view
from app.database import Database
from app.knowledge.vector_store import rebuild_knowledge_index
from app.learning.feedback import FeedbackService
from app.learning.learning_report import LearningReport
from app.learning.ml_model import FutureMLModel
from app.logger import setup_logging
from app.notifications.notification_service import NotificationService
from app.scheduler import CryptoRadarService


PROJECT_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="CryptoRadar",
        description="Backend-only crypto signal notification bot. It never trades.",
    )
    parser.add_argument("--mock", action="store_true", help="Run with simulated market data.")
    parser.add_argument("--scan-now", action="store_true", help="Run one scan and exit.")
    parser.add_argument("--test-telegram", action="store_true", help="Send a Telegram test message.")
    parser.add_argument("--test-ai", action="store_true", help="Send a short test prompt to LM Studio.")
    parser.add_argument(
        "--test-telegram-format",
        dest="test_telegram_format",
        action="store_true",
        help="Format a fake signal with the fixed Telegram template and optionally send it.",
    )
    parser.add_argument(
        "--test-live-notification",
        action="store_true",
        help="Send a fake BUY signal through the real notification path.",
    )
    parser.add_argument("--show-config", action="store_true", help="Print sanitized config.")
    parser.add_argument("--rebuild-knowledge", action="store_true", help="Rebuild the local knowledge index.")
    parser.add_argument("--collect-market-data-now", action="store_true", help="Collect broad Binance Spot market data for ML.")
    parser.add_argument("--data-coverage-report", action="store_true", help="Show broad market data coverage.")
    parser.add_argument("--train-ml-model", action="store_true", help="Train the local ML filter from labeled signal history.")
    parser.add_argument("--ml-report", action="store_true", help="Show local ML training and prediction status.")
    parser.add_argument("--daily-summary", action="store_true", help="Send a daily summary immediately.")
    parser.add_argument("--top-signals", action="store_true", help="Print the current best signals.")
    parser.add_argument("--learning-report", action="store_true", help="Print the learning report.")
    parser.add_argument(
        "--mark-signal",
        nargs=2,
        metavar=("SIGNAL_ID", "RESULT"),
        help="Mark a signal as win, loss, or neutral.",
    )
    return parser


async def async_main() -> int:
    args = build_parser().parse_args()
    config = load_config(PROJECT_ROOT / "config.yaml", PROJECT_ROOT / ".env")
    setup_logging(PROJECT_ROOT)
    db = Database(PROJECT_ROOT / config["storage"]["sqlite_path"])
    db.initialize()

    if args.show_config:
        print(json.dumps(safe_config_view(config), indent=2))
        return 0

    if args.mark_signal:
        signal_id, result = args.mark_signal
        if result not in {"win", "loss", "neutral"}:
            print("RESULT must be one of: win, loss, neutral", file=sys.stderr)
            return 2
        FeedbackService(db).mark(signal_id, result)
        print(f"Marked {signal_id} as {result}.")
        return 0

    if args.learning_report:
        print(LearningReport(db, config).render_text())
        return 0

    notifier = NotificationService(config, db)

    if args.test_telegram:
        sent = notifier.send_test()
        print("Telegram test sent." if sent else "Telegram test skipped or failed. Check token/chat config.")
        return 0

    if args.test_ai:
        response = LMStudioClient(config).chat(
            "You are a local AI health-check assistant. Keep the reply short.",
            "Reply with one sentence confirming LM Studio local chat is working for CryptoRadar.",
        )
        if response:
            print(response)
        else:
            print("LM Studio did not respond. Check that it is running at ai.base_url and that ai.model is loaded.")
        return 0

    if args.test_telegram_format:
        fake_signal = build_fake_buy_signal()
        formatted = TelegramMessageFormatter(config).format(fake_signal)
        print(formatted)
        if config["notifications"].get("telegram_enabled", True):
            notifier.send_text(formatted, signal=fake_signal)
        return 0

    if args.test_live_notification:
        fake_signal = build_fake_buy_signal()
        sent = notifier.notify_signal(fake_signal)
        print("Live notification path sent." if sent else "Live notification path skipped or failed. Check thresholds, cooldown, and Telegram config.")
        return 0

    if args.rebuild_knowledge:
        summary = rebuild_knowledge_index(config, db, PROJECT_ROOT)
        print(summary)
        return 0

    if args.collect_market_data_now:
        summary = BroadMarketCollector(config, db).collect_now(lambda message: print(message, flush=True))
        print(json.dumps(summary, indent=2))
        return 0

    if args.data_coverage_report:
        print(BroadMarketCollector(config, db).coverage_report())
        return 0

    if args.train_ml_model:
        print(FutureMLModel(db, config, PROJECT_ROOT).train())
        return 0

    if args.ml_report:
        print(FutureMLModel(db, config, PROJECT_ROOT).report())
        return 0

    service = CryptoRadarService(config=config, db=db, project_root=PROJECT_ROOT, mock=args.mock)

    if args.daily_summary:
        summary = service.build_daily_summary()
        notifier.send_daily_summary(summary)
        print(summary)
        return 0

    if args.top_signals:
        signals = service.top_signals()
        for signal in signals:
            print(f"{signal['signal_type']:9} {signal['symbol']:12} score={signal['score']:3} risk={signal['risk_level']}")
        if not signals:
            print("No signals stored yet. Run --scan-now or let the service collect data.")
        return 0

    if args.scan_now:
        signals = await service.scan_once()
        print(f"Scan complete. Generated {len(signals)} signal(s).")
        for signal in signals[:10]:
            print(f"{signal['signal_type']:9} {signal['symbol']:12} score={signal['score']:3} {signal['main_reason']}")
        return 0

    await service.run_forever()
    return 0


def build_fake_buy_signal() -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return {
        "id": f"test-live-{timestamp}",
        "symbol": f"TEST{timestamp[-4:]}USDT",
        "signal_type": "BUY",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "price": 142.5,
        "score": 75,
        "confidence": "Medium",
        "risk_level": "Medium",
        "timeframe": "15m",
        "main_reason": "Breakout with strong relative volume while BTC trend is supportive.",
        "indicators": {
            "rsi": 61.4,
            "macd_histogram": 0.18,
            "ema_alignment": "bullish",
            "relative_volume": 2.1,
        },
        "features": {"trend": "uptrend", "change_24h": 4.8},
        "btc_trend": "bullish",
        "eth_trend": "sideways",
        "possible_entry_zone": "140.50-142.50",
        "possible_take_profit_zones": [146.0, 150.0],
        "possible_stop_loss_zone": 137.8,
        "invalidation_level": 137.8,
        "warning": "Do not chase if price moves too far above the entry zone.",
        "knowledge_sources_used": [],
    }


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
