from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.config import load_config, safe_config_view
from app.database import Database
from app.knowledge.vector_store import rebuild_knowledge_index
from app.learning.feedback import FeedbackService
from app.learning.learning_report import LearningReport
from app.logger import setup_logging
from app.notifications.notification_service import NotificationService
from app.scheduler import CryptoRadarService


PROJECT_ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="CryptoRadar",
        description="Backend-only crypto signal notification bot. It never trades.",
    )
    parser.add_argument("--mock", action="store_true", help="Run with simulated market data.")
    parser.add_argument("--scan-now", action="store_true", help="Run one scan and exit.")
    parser.add_argument("--test-telegram", action="store_true", help="Send a Telegram test message.")
    parser.add_argument("--show-config", action="store_true", help="Print sanitized config.")
    parser.add_argument("--rebuild-knowledge", action="store_true", help="Rebuild the local knowledge index.")
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

    if args.rebuild_knowledge:
        summary = rebuild_knowledge_index(config, db, PROJECT_ROOT)
        print(summary)
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
