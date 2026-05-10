from __future__ import annotations

import os
import ast
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - PyYAML is in requirements.
    yaml = None


DEFAULT_CONFIG: dict[str, Any] = {
    "binance": {
        "quote_assets": ["USDT"],
        "min_24h_volume_usdt": 5_000_000,
        "max_symbols_to_analyze": 150,
        "refresh_symbols_hours": 6,
        "priority_symbols": ["BTCUSDT", "ETHUSDT"],
        "ignored_symbols": [],
        "newly_listed_symbols": [],
        "stablecoin_symbols": ["USDTUSDT", "USDCUSDT", "FDUSDUSDT"],
        "watchlist_symbols": [],
        "monitoring_mode": "high_volume",
    },
    "collector": {
        "enabled": True,
        "collect_all_active_spot": True,
        "quote_assets": ["USDT"],
        "min_24h_volume_usdt": 0,
        "max_symbols_per_cycle": 1000,
        "include_low_data_symbols": True,
        "interval_minutes": 30,
        "fetch_candles": "auto",
        "candle_min_24h_volume_usdt": 5_000_000,
        "max_candle_symbols_per_cycle": 120,
        "candle_interval": "15m",
        "candle_limit": 500,
    },
    "automation": {
        "enabled": True,
        "collect_market_data": True,
        "scan_market": True,
        "auto_train_ml": True,
        "ml_train_interval_minutes": 60,
        "ml_retrain_new_labels": 100,
        "learning_report_interval_minutes": 60,
        "status_interval_minutes": 10,
        "health_check_interval_seconds": 300,
    },
    "backtest": {
        "enabled": True,
        "default_timeframe": "15m",
        "default_days": 30,
        "lookback_candles": 220,
        "max_symbols": 50,
        "horizons": ["1h", "4h", "24h"],
        "auto_run": True,
        "interval_hours": 24,
    },
    "coin_alerts": {
        "enabled": True,
        "default_quote": "USDT",
        "interval_seconds": 300,
        "cooldown_minutes": 30,
        "preferred_interval_seconds": 180,
        "preferred_cooldown_minutes": 15,
        "candle_interval": "15m",
        "candle_limit": 96,
        "surge_24h_pct": 10,
        "dump_24h_pct": -8,
        "surge_1h_pct": 4,
        "dump_1h_pct": -4,
        "volume_spike_ratio": 2.0,
        "near_high_pct": 2.0,
        "high_risk_pump_pct": 20,
        "watchlist_auto_alerts": True,
        "preferred_auto_alerts": True,
    },
    "news": {
        "enabled": True,
        "sources": [
            {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
            {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss.xml"},
        ],
        "interval_minutes": 15,
        "lookback_hours_on_prefer": 72,
        "max_news_per_coin_on_add": 3,
        "importance_threshold": 70,
        "per_symbol_cooldown_minutes": 60,
        "max_news_alerts_per_hour": 6,
        "ml_breakout_probability_threshold": 0.65,
    },
    "scanner": {
        "scan_interval_seconds": 30,
        "buy_score_threshold": 70,
        "sell_score_threshold": 70,
        "high_risk_threshold": 65,
        "cooldown_minutes": 30,
        "timeframes": ["5m", "15m", "1h", "4h", "1d"],
    },
    "ai": {
        "enabled": True,
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
        "embedding_model": "nomic-embed-text",
        "temperature": 0.2,
        "max_tokens": 700,
        "timeout_seconds": 15,
        "reasoning_effort": "none",
        "analysis_reasoning_effort": "none",
        "analysis_max_tokens": 300,
        "analysis_timeout_seconds": 3,
    },
    "knowledge": {
        "folder": "./knowledge",
        "vector_db": "./data/vector_db",
        "rebuild_on_start": False,
        "chunk_size": 1200,
        "chunk_overlap": 160,
        "top_k": 5,
    },
    "learning": {
        "enabled": True,
        "min_samples_before_weight_change": 30,
        "weight_update_strength": 0.05,
        "track_after_minutes": [15, 60, 240, 1440, 10080],
        "auto_adjust_weights": True,
        "manual_feedback_enabled": True,
        "performance_thresholds": {
            "buy_win_pct": 2.5,
            "buy_loss_pct": -1.5,
            "sell_win_pct": 2.0,
            "sell_loss_pct": -2.0,
            "high_risk_win_pct": 3.0,
            "high_risk_loss_pct": -3.0,
            "neutral_after_minutes": 240,
        },
    },
    "ml": {
        "enabled": True,
        "min_training_samples": 30,
        "sample_warning_threshold": 200,
        "min_positive_samples_warning": 30,
        "random_forest_min_samples": 200,
        "test_size": 0.25,
        "model_path": "./models/latest_model.pkl",
        "training_examples_min_confidence": 0,
        "auto_label_after_minutes": 240,
    },
    "notifications": {
        "telegram_enabled": True,
        "desktop_enabled": False,
        "email_enabled": False,
        "discord_enabled": False,
        "notify_buy": True,
        "notify_sell": True,
        "notify_hold": False,
        "notify_wait": False,
        "notify_avoid": False,
        "notify_high_risk": True,
        "max_alerts_per_hour": 10,
        "only_strong_signals": True,
        "notify_startup": True,
        "notify_errors": True,
        "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
    },
    "telegram": {"bot_token_env": "TELEGRAM_BOT_TOKEN", "chat_id_env": "TELEGRAM_CHAT_ID"},
    "email": {
        "user_env": "EMAIL_USER",
        "password_env": "EMAIL_PASSWORD",
        "to": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
    },
    "discord": {"webhook_env": "DISCORD_WEBHOOK_URL"},
    "storage": {"sqlite_path": "./data/cryptoradar.db"},
    "telegram_formatting": {
        "use_template_formatter": True,
        "max_message_chars": 1200,
        "style": "clean_professional",
        "include_emojis": True,
        "include_key_levels": True,
        "include_risk_note": True,
    },
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path, env_path: Path | None = None) -> dict[str, Any]:
    if env_path is not None:
        load_env(env_path)
    loaded: dict[str, Any] = {}
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        if yaml is None:
            loaded = parse_simple_yaml(text)
        else:
            loaded = yaml.safe_load(text) or {}
    return deep_merge(DEFAULT_CONFIG, loaded)


def safe_config_view(config: dict[str, Any]) -> dict[str, Any]:
    view = deepcopy(config)
    for section in ("telegram", "email", "discord"):
        if section in view:
            for key, value in view[section].items():
                if key.endswith("_env"):
                    view[section][key] = value
    return view


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Small fallback parser for this project's simple config.yaml shape."""

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(raw_value)
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    try:
        return ast.literal_eval(value)
    except Exception:
        pass
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip("\"'")
