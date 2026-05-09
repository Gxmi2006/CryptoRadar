from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_CONFIG
from app.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "cryptoradar_test.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def config(tmp_path: Path) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["ai"]["enabled"] = False
    cfg["ai"]["provider"] = "none"
    cfg["knowledge"]["folder"] = str(tmp_path / "knowledge")
    cfg["knowledge"]["vector_db"] = str(tmp_path / "vector_db")
    cfg["notifications"]["telegram_enabled"] = False
    cfg["notifications"]["desktop_enabled"] = False
    cfg["notifications"]["email_enabled"] = False
    cfg["notifications"]["discord_enabled"] = False
    return cfg
