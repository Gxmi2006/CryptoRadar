from __future__ import annotations

import asyncio
from pathlib import Path

from app.scheduler import CryptoRadarService


class FakeCollector:
    def __init__(self) -> None:
        self.calls = 0

    def collect_now(self, progress=None) -> dict:
        self.calls += 1
        if progress:
            progress("fake collector progress")
        return {"collected": 3, "candle_symbols": 1}


class FailingCollector:
    def collect_now(self, progress=None) -> dict:
        raise RuntimeError("collector unavailable")


class FakeML:
    def __init__(self) -> None:
        self.calls = 0

    def train(self) -> str:
        self.calls += 1
        return "Need at least 30 labeled win/loss examples before training. Current examples: 0."


def test_auto_pipeline_run_once_invokes_collector_scan_and_ml(config: dict, db, tmp_path: Path) -> None:
    config["automation"]["collect_market_data"] = True
    config["automation"]["scan_market"] = True
    config["automation"]["auto_train_ml"] = True
    service = CryptoRadarService(config, db, tmp_path, mock=True)
    collector = FakeCollector()
    ml = FakeML()
    service.collector = collector
    service.ml = ml
    messages: list[str] = []

    asyncio.run(service.run_auto_pipeline(run_once=True, status=messages.append))

    assert collector.calls == 1
    assert ml.calls == 1
    assert db.query_one("SELECT COUNT(*) AS count FROM scanner_health")["count"] == 1
    assert any("Scan complete" in message for message in messages)
    assert any("ML training:" in message for message in messages)
    assert any("Status:" in message for message in messages)


def test_auto_pipeline_continues_when_collector_fails(config: dict, db, tmp_path: Path) -> None:
    config["automation"]["collect_market_data"] = True
    config["automation"]["scan_market"] = True
    config["automation"]["auto_train_ml"] = False
    service = CryptoRadarService(config, db, tmp_path, mock=True)
    service.collector = FailingCollector()
    messages: list[str] = []

    asyncio.run(service.run_auto_pipeline(run_once=True, status=messages.append))

    assert db.query_one("SELECT COUNT(*) AS count FROM scanner_health")["count"] == 1
    assert any("Broad market collection failed" in message for message in messages)


def test_auto_pipeline_ml_training_handles_too_few_samples(config: dict, db, tmp_path: Path) -> None:
    config["automation"]["collect_market_data"] = False
    config["automation"]["scan_market"] = False
    config["automation"]["auto_train_ml"] = True
    service = CryptoRadarService(config, db, tmp_path, mock=True)
    messages: list[str] = []

    asyncio.run(service.run_auto_pipeline(run_once=True, status=messages.append))

    row = db.query_one("SELECT report_text FROM ml_training_runs ORDER BY id DESC LIMIT 1")
    assert row is None
    assert any("Need at least 30" in message for message in messages)


def test_powershell_runner_starts_auto_pipeline() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_cryptoradar.ps1"
    text = script.read_text(encoding="utf-8")
    assert "--auto-pipeline" in text
    assert "main.py" in text
