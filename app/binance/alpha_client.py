from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import httpx
except Exception:  # pragma: no cover - urllib fallback is enough.
    httpx = None


log = logging.getLogger(__name__)


class BinanceAlphaClient:
    """Read-only Binance Alpha public-data client."""

    BASE_URL = "https://www.binance.com"

    def __init__(self, base_url: str | None = None, timeout: float = 12.0, retries: int = 3):
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def get_token_list(self) -> list[dict[str, Any]]:
        data = self._get("/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list")
        rows = data.get("data", []) if isinstance(data, dict) else []
        return rows if isinstance(rows, list) else []

    def resolve_token(self, coin_id: str) -> dict[str, Any] | None:
        target = normalize_alpha_input(coin_id)
        for token in self.get_token_list():
            alpha_id = str(token.get("alphaId") or "").upper()
            symbol = str(token.get("symbol") or "").upper()
            name = str(token.get("name") or "").upper()
            trade_symbol = f"{alpha_id}USDT" if alpha_id else ""
            if bool(token.get("offline")) or bool(token.get("fullyDelisted")):
                continue
            if target in {alpha_id, trade_symbol, symbol, name.replace(" ", "")}:
                return {**token, "tradeSymbol": trade_symbol}
        return None

    def get_ticker(self, trade_symbol: str) -> dict[str, Any]:
        data = self._get("/bapi/defi/v1/public/alpha-trade/ticker", {"symbol": trade_symbol})
        payload = data.get("data", {}) if isinstance(data, dict) else {}
        return payload if isinstance(payload, dict) else {}

    def get_klines(self, trade_symbol: str, interval: str, limit: int = 96) -> list[dict[str, float]]:
        data = self._get("/bapi/defi/v1/public/alpha-trade/klines", {"symbol": trade_symbol, "interval": interval, "limit": limit})
        rows = data.get("data", []) if isinstance(data, dict) else []
        return [parse_alpha_kline(row) for row in rows if isinstance(row, list) and len(row) >= 7]

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                if httpx is not None:
                    with httpx.Client(timeout=self.timeout, headers={"User-Agent": "CryptoRadar/1.0"}) as client:
                        response = client.get(url)
                        response.raise_for_status()
                        return response.json()
                request = Request(url, headers={"User-Agent": "CryptoRadar/1.0"})
                with urlopen(request, timeout=self.timeout) as response:  # nosec - public Binance URL.
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                wait = min(2**attempt, 8)
                log.warning("Binance Alpha retry %s for %s after %s", attempt + 1, path, type(exc).__name__)
                time.sleep(wait)
        raise RuntimeError(f"Binance Alpha public request failed for {path}: {last_error}")


def parse_alpha_kline(raw: list[Any]) -> dict[str, float]:
    return {
        "open_time": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time": int(raw[6]),
        "quote_volume": float(raw[7]) if len(raw) > 7 else 0.0,
        "trades": float(raw[8]) if len(raw) > 8 else 0.0,
    }


def normalize_alpha_input(value: str) -> str:
    return value.strip().upper().replace("/", "").replace("-", "").replace(" ", "")
