from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

try:
    import websockets
except Exception:  # pragma: no cover - optional until live streaming is used.
    websockets = None


log = logging.getLogger(__name__)


SPOT_STREAM_URL = "wss://stream.binance.com:9443/ws"


def parse_mini_ticker_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_time": int(event.get("E", 0)),
        "symbol": event.get("s", ""),
        "close": float(event.get("c", 0)),
        "open": float(event.get("o", 0)),
        "high": float(event.get("h", 0)),
        "low": float(event.get("l", 0)),
        "base_volume": float(event.get("v", 0)),
        "quote_volume": float(event.get("q", 0)),
    }


def parse_rolling_ticker_event(event: dict[str, Any], window: str) -> dict[str, Any]:
    last = float(event.get("c", 0))
    open_price = float(event.get("o", 0))
    change = ((last - open_price) / open_price * 100) if open_price else 0.0
    return {
        "window": window,
        "symbol": event.get("s", ""),
        "price": last,
        "change_pct": change,
        "quote_volume": float(event.get("q", 0)),
    }


class BinanceSpotMarketStream:
    """All-market Spot stream reader with exponential reconnect."""

    def __init__(self, stream: str = "!miniTicker@arr", base_url: str = SPOT_STREAM_URL):
        self.stream = stream
        self.base_url = base_url.rstrip("/")

    async def events(self) -> AsyncIterator[list[dict[str, Any]]]:
        if websockets is None:
            raise RuntimeError("websockets package is required for live streams")
        url = f"{self.base_url}/{self.stream}"
        backoff = 1
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    log.info("Connected Binance stream: %s", self.stream)
                    backoff = 1
                    async for raw in ws:
                        payload = json.loads(raw)
                        if isinstance(payload, list):
                            yield payload
                        else:
                            yield [payload]
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Binance stream reconnect after %s: %s", type(exc).__name__, self.stream)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def run(self, handler: Callable[[list[dict[str, Any]]], Any]) -> None:
        async for batch in self.events():
            await handler(batch)
