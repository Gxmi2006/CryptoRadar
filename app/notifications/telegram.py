from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


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
        if httpx is not None:
            with httpx.Client(timeout=12) as client:
                response = client.post(url, data=payload)
                return response.status_code < 400
        body = urlencode(payload).encode("utf-8")
        request = Request(url, data=body)
        with urlopen(request, timeout=12) as response:  # nosec - Telegram bot API.
            data = json.loads(response.read().decode("utf-8"))
            return bool(data.get("ok"))
