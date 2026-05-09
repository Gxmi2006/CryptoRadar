from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


class DiscordNotifier:
    def __init__(self, config: dict[str, Any]):
        env_name = config.get("discord", {}).get("webhook_env", "DISCORD_WEBHOOK_URL")
        self.webhook = os.getenv(env_name, "")

    def send(self, message: str) -> bool:
        if not self.webhook:
            return False
        if httpx is not None:
            with httpx.Client(timeout=12) as client:
                response = client.post(self.webhook, json={"content": message})
                return response.status_code < 400
        body = json.dumps({"content": message}).encode("utf-8")
        request = Request(self.webhook, data=body, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=12) as response:  # nosec - configured webhook.
            return response.status < 400
