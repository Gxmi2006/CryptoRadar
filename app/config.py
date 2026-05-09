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
    },
    "notifications": {
        "telegram_enabled": True,
        "desktop_enabled": False,
        "email_enabled": False,
        "discord_enabled": False,
        "max_alerts_per_hour": 10,
        "only_strong_signals": True,
        "notify_startup": False,
        "notify_errors": False,
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
    "storage": {"sqlite_path": "./data/cryptoradar.sqlite3"},
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
