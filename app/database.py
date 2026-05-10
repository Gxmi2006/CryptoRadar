from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(sql, rows)

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def loads(value: str | None, default: Any = None) -> Any:
        if value is None:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default


SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY,
    base_asset TEXT,
    quote_asset TEXT,
    status TEXT,
    active INTEGER,
    volume_usdt REAL,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    price REAL,
    change_1h REAL,
    change_4h REAL,
    change_24h REAL,
    volume_usdt REAL,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broad_market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    base_asset TEXT,
    quote_asset TEXT,
    price REAL,
    change_1h REAL,
    change_4h REAL,
    change_24h REAL,
    volume_usdt REAL,
    high_24h REAL,
    low_24h REAL,
    data_quality TEXT,
    quality_reasons_json TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS symbol_data_quality (
    symbol TEXT PRIMARY KEY,
    data_quality TEXT,
    quality_reasons_json TEXT,
    volume_usdt REAL,
    candle_count INTEGER,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT,
    interval TEXT,
    open_time INTEGER,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    close_time INTEGER,
    PRIMARY KEY (symbol, interval, open_time)
);

CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT,
    signal_type TEXT,
    created_at TEXT,
    price REAL,
    score INTEGER,
    confidence TEXT,
    risk_level TEXT,
    timeframe TEXT,
    main_reason TEXT,
    payload_json TEXT,
    final_result TEXT DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS signal_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    buy_score INTEGER,
    sell_score INTEGER,
    hold_score INTEGER,
    wait_score INTEGER,
    avoid_score INTEGER,
    high_risk_score INTEGER,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS ai_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    provider TEXT,
    model TEXT,
    analysis_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_sources (
    id TEXT PRIMARY KEY,
    file_name TEXT,
    source_title TEXT,
    author TEXT,
    source_date TEXT,
    category TEXT,
    trust_level TEXT,
    enabled INTEGER,
    notes TEXT,
    performance_score REAL,
    warnings_json TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    file_name TEXT,
    chunk_index INTEGER,
    text TEXT,
    embedding_json TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    source_id TEXT,
    file_name TEXT,
    chunk_id TEXT,
    quote TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    symbol TEXT,
    channel TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    link TEXT,
    published_at TEXT,
    matched_symbols_json TEXT,
    sentiment TEXT,
    importance_score INTEGER,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id TEXT,
    symbol TEXT,
    channel TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(news_id, symbol, channel)
);

CREATE TABLE IF NOT EXISTS preferred_coins (
    symbol TEXT PRIMARY KEY,
    category TEXT,
    added_time TEXT DEFAULT CURRENT_TIMESTAMP,
    alert_sensitivity TEXT,
    cooldown_minutes INTEGER,
    notes TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS holdings (
    symbol TEXT PRIMARY KEY,
    entry_price REAL,
    amount REAL,
    category TEXT,
    added_time TEXT DEFAULT CURRENT_TIMESTAMP,
    alert_settings TEXT,
    last_alert_time TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id TEXT PRIMARY KEY,
    signal_id TEXT,
    symbol TEXT,
    side TEXT,
    status TEXT,
    entry_price REAL,
    current_price REAL,
    take_profit REAL,
    stop_loss REAL,
    invalidation REAL,
    max_profit_pct REAL DEFAULT 0,
    max_drawdown_pct REAL DEFAULT 0,
    result TEXT DEFAULT 'unknown',
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signal_performance (
    signal_id TEXT PRIMARY KEY,
    price_15m REAL,
    price_1h REAL,
    price_4h REAL,
    price_24h REAL,
    price_7d REAL,
    max_profit_pct REAL,
    max_drawdown_pct REAL,
    take_profit_reached INTEGER,
    stop_loss_reached INTEGER,
    final_result TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS adaptive_weights (
    key TEXT PRIMARY KEY,
    value REAL,
    min_value REAL,
    max_value REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS manual_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    result TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_text TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ml_training_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE,
    symbol TEXT,
    signal_type TEXT,
    label INTEGER,
    features_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ml_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    symbol TEXT,
    success_probability REAL,
    risk_score REAL,
    confidence_score REAL,
    data_quality TEXT,
    model_version TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ml_training_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT,
    model_type TEXT,
    sample_count INTEGER,
    train_count INTEGER,
    test_count INTEGER,
    accuracy REAL,
    report_text TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    timeframe TEXT,
    days INTEGER,
    max_symbols INTEGER,
    symbol_filter TEXT,
    lookback_candles INTEGER,
    horizons_json TEXT,
    status TEXT,
    signal_count INTEGER DEFAULT 0,
    report_text TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    strategy TEXT,
    symbol TEXT,
    signal_type TEXT,
    score INTEGER,
    timeframe TEXT,
    open_time INTEGER,
    price REAL,
    future_return_pct REAL,
    max_favorable_pct REAL,
    max_drawdown_pct REAL,
    success INTEGER,
    false_positive INTEGER,
    data_quality TEXT,
    payload_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scanner_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
