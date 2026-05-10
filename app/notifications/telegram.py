from __future__ import annotations

import os
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramNotifier:
    def __init__(self, config: dict[str, Any]):
        telegram_cfg = config.get("telegram", {})
        self.token = os.getenv(telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
        self.chat_id = os.getenv(telegram_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str) -> bool:
        if not self.configured:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "disable_web_page_preview": True}
        body = urlencode(payload).encode("utf-8")
        request = Request(url, data=body)
        with urlopen(request, timeout=12) as response:  # nosec - Telegram bot API.
            return response.status < 400

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict[str, Any]]:
        if not self.token:
            return []
        params: dict[str, Any] = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{self.token}/getUpdates?{urlencode(params)}"
        request = Request(url)
        with urlopen(request, timeout=timeout + 10) as response:  # nosec - Telegram bot API.
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            return []
        result = payload.get("result", [])
        return result if isinstance(result, list) else []
