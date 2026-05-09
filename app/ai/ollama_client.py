from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 45.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            url = f"{self.base_url}/api/tags"
            if httpx is not None:
                with httpx.Client(timeout=1.5) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return True
            request = Request(url)
            with urlopen(request, timeout=1.5):  # nosec - local Ollama URL.
                return True
        except Exception:
            return False

    def generate(self, model: str, prompt: str, temperature: float = 0.2, max_tokens: int = 700) -> str | None:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            data = self._post("/api/generate", payload)
            return data.get("response", "")
        except Exception as exc:
            log.warning("Ollama generate unavailable: %s", type(exc).__name__)
            return None

    def embed(self, model: str, text: str) -> list[float] | None:
        payload = {"model": model, "prompt": text}
        try:
            data = self._post("/api/embeddings", payload)
            vector = data.get("embedding")
            return [float(value) for value in vector] if vector else None
        except Exception:
            return None

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        if httpx is not None:
            with httpx.Client(timeout=5) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        request = Request(url)
        with urlopen(request, timeout=5) as response:  # nosec - local Ollama URL.
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        if httpx is not None:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:  # nosec - local Ollama URL.
            return json.loads(response.read().decode("utf-8"))
