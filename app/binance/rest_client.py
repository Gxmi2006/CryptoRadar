from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import httpx
except Exception:  # pragma: no cover - urllib fallback is tested by construction.
    httpx = None


log = logging.getLogger(__name__)


class BinancePublicRestClient:
    """Read-only Binance Spot REST client.

    This class intentionally exposes market-data endpoints only. It does not
    accept API keys and contains no account, execution, or fund-movement APIs.
    """

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(self, base_url: str | None = None, timeout: float = 12.0, retries: int = 3):
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def get_exchange_info(self) -> dict[str, Any]:
        return self._get("/exchangeInfo")

    def get_24hr_tickers(self) -> list[dict[str, Any]]:
        data = self._get("/ticker/24hr")
        return data if isinstance(data, list) else [data]

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> list[list[Any]]:
        return self._get("/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    def get_ticker_price(self, symbol: str) -> dict[str, Any]:
        return self._get("/ticker/price", {"symbol": symbol})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                if httpx is not None:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.get(url)
                        response.raise_for_status()
                        return response.json()
                request = Request(url, headers={"User-Agent": "CryptoRadar/1.0"})
                with urlopen(request, timeout=self.timeout) as response:  # nosec - public Binance URL.
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                wait = min(2**attempt, 8)
                log.warning("Binance REST retry %s for %s after %s", attempt + 1, path, type(exc).__name__)
                time.sleep(wait)
        raise RuntimeError(f"Binance public REST request failed for {path}: {last_error}")


def parse_kline(raw: list[Any]) -> dict[str, float]:
    return {
        "open_time": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time": int(raw[6]),
        "quote_volume": float(raw[7]),
        "trades": float(raw[8]),
    }
