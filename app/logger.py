from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _handler(path: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    return handler


def setup_logging(project_root: Path) -> None:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s - %(message)s"))
    root.addHandler(console)
    root.addHandler(_handler(log_dir / "app.log", logging.INFO))
    root.addHandler(_handler(log_dir / "errors.log", logging.ERROR))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    for name, file_name in {"signals": "signals.log", "learning": "learning.log"}.items():
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = True
        logger.addHandler(_handler(log_dir / file_name, logging.INFO))
