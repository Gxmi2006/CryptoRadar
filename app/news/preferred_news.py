from __future__ import annotations

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.request import Request, urlopen
from xml.etree import ElementTree

try:
    import httpx
except Exception:  # pragma: no cover - urllib fallback keeps RSS optional.
    httpx = None

from app.alerts.coin_alerts import CoinAlertService, format_pct
from app.storage.user_lists import UserListStore


log = logging.getLogger(__name__)


BULLISH_KEYWORDS = {
    "listing": 28,
    "binance alpha": 28,
    "binance": 18,
    "partnership": 18,
    "mainnet": 16,
    "airdrop": 14,
    "etf": 14,
    "upgrade": 12,
    "integrates": 12,
    "launch": 12,
    "surge": 10,
    "rally": 10,
    "whale": 8,
}

BEARISH_KEYWORDS = {
    "hack": 35,
    "exploit": 35,
    "delisting": 30,
    "lawsuit": 24,
    "sec": 18,
    "outage": 18,
    "unlock": 16,
    "investigation": 16,
    "scam": 24,
    "dump": 18,
    "plunge": 16,
}


@dataclass(frozen=True)
class NewsItem:
    id: str
    source: str
    title: str
    link: str
    published_at: str
    summary: str = ""


class PreferredNewsService:
    def __init__(
        self,
        config: dict[str, Any],
        db: Any,
        coin_alerts: CoinAlertService,
        notifier: Any,
        fetcher: Any | None = None,
    ):
        self.config = config
        self.db = db
        self.coin_alerts = coin_alerts
        self.notifier = notifier
        self.fetcher = fetcher or fetch_url

    def check_preferred_news(self, force: bool = False) -> list[dict[str, Any]]:
        if not self.config.get("news", {}).get("enabled", True):
            return []
        results: list[dict[str, Any]] = []
        self.refresh_news_items()
        for row in UserListStore(self.db).preferred():
            results.extend(self.check_coin_news(str(row["symbol"]), force=force))
        return results

    def check_coin_news(self, coin_id: str, force: bool = False, max_items: int | None = None) -> list[dict[str, Any]]:
        if not self.config.get("news", {}).get("enabled", True):
            return []
        market = self.coin_alerts.resolve_market(coin_id)
        aliases = symbol_aliases(market)
        items = self.refresh_news_items()
        matched = [score_news_item(item, aliases) for item in items]
        lookback = int(self.config.get("news", {}).get("lookback_hours_on_prefer", 72))
        matched = recent_only(matched, lookback)
        threshold = int(self.config.get("news", {}).get("importance_threshold", 70))
        filtered = [item for item in matched if item["importance_score"] >= threshold]
        filtered.sort(key=lambda item: (item["importance_score"], item["published_at"]), reverse=True)
        limit = max_items if max_items is not None else int(self.config.get("news", {}).get("max_news_per_coin_on_add", 3))
        alerts: list[dict[str, Any]] = []
        market_alert = self._safe_market_alert(market)
        for item in filtered[:limit]:
            self._store_news_item(item, [market["symbol"]])
            message = format_preferred_news_alert(market, item, market_alert)
            alert = {
                "news_id": item["id"],
                "symbol": market["symbol"],
                "title": item["title"],
                "source": item["source"],
                "importance_score": item["importance_score"],
                "sentiment": item["sentiment"],
                "message": message,
                "sent": False,
            }
            if force or self._can_send(market["symbol"], item["id"]):
                sent = self.notifier.send_text(message, signal={"id": f"news-{item['id']}", "symbol": market["symbol"]})
                alert["sent"] = sent
                self._record_news_alert(item["id"], market["symbol"], "telegram", "sent" if sent else "skipped_or_failed", message)
            alerts.append(alert)
        return alerts

    def format_coin_news_summary(self, coin_id: str) -> str:
        market = self.coin_alerts.resolve_market(coin_id)
        aliases = symbol_aliases(market)
        items = [score_news_item(item, aliases) for item in self.refresh_news_items()]
        items = [item for item in items if item["importance_score"] > 0]
        items.sort(key=lambda item: (item["importance_score"], item["published_at"]), reverse=True)
        market_alert = self._safe_market_alert(market)
        if not items:
            return format_no_news_message(market, market_alert)
        return format_preferred_news_alert(market, items[0], market_alert)

    def refresh_news_items(self) -> list[dict[str, Any]]:
        cfg = self.config.get("news", {})
        items: list[NewsItem] = []
        for source in cfg.get("sources", []):
            name = str(source.get("name", "RSS"))
            url = str(source.get("url", ""))
            if not url:
                continue
            try:
                xml_text = self.fetcher(url)
                items.extend(parse_rss_items(xml_text, name))
            except Exception as exc:
                log.warning("News feed failed for %s: %s", name, type(exc).__name__)
        rows = [item_to_dict(item) for item in items]
        for item in rows:
            self._store_news_item(item, [])
        return rows

    def _safe_market_alert(self, market: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.coin_alerts.build_alert(market, preferred=True)
        except Exception as exc:
            log.warning("Preferred news market context failed for %s: %s", market.get("symbol"), type(exc).__name__)
            return {"symbol": market.get("symbol"), "display_symbol": market.get("display_symbol"), "events": [], "ml_prediction": None}

    def _store_news_item(self, item: dict[str, Any], symbols: list[str]) -> None:
        existing = self.db.query_one("SELECT matched_symbols_json FROM news_items WHERE id=?", (item["id"],))
        existing_symbols = set(self.db.loads(existing.get("matched_symbols_json") if existing else None, []))
        existing_symbols.update(symbols)
        self.db.execute(
            """
            INSERT INTO news_items(
                id, source, title, link, published_at, matched_symbols_json,
                sentiment, importance_score, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                matched_symbols_json=excluded.matched_symbols_json,
                sentiment=excluded.sentiment,
                importance_score=MAX(news_items.importance_score, excluded.importance_score),
                payload_json=excluded.payload_json
            """,
            (
                item["id"],
                item["source"],
                item["title"],
                item["link"],
                item["published_at"],
                self.db.dumps(sorted(existing_symbols)),
                item.get("sentiment", "neutral"),
                int(item.get("importance_score", 0)),
                self.db.dumps(item),
            ),
        )

    def _can_send(self, symbol: str, news_id: str) -> bool:
        if self.db.query_one("SELECT id FROM news_alerts WHERE news_id=? AND symbol=? AND status='sent'", (news_id, symbol)):
            return False
        cfg = self.config.get("news", {})
        per_symbol = int(cfg.get("per_symbol_cooldown_minutes", 60))
        last = self.db.query_one(
            """
            SELECT created_at FROM news_alerts
            WHERE symbol=? AND status='sent'
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (symbol,),
        )
        if last and _age_minutes(str(last["created_at"])) < per_symbol:
            return False
        hourly_limit = int(cfg.get("max_news_alerts_per_hour", 6))
        hourly = self.db.query_one(
            "SELECT COUNT(*) AS count FROM news_alerts WHERE datetime(created_at) >= datetime('now', '-1 hour') AND status='sent'"
        )
        return int(hourly["count"]) < hourly_limit if hourly else True

    def _record_news_alert(self, news_id: str, symbol: str, channel: str, status: str, message: str) -> None:
        self.db.execute(
            """
            INSERT INTO news_alerts(news_id, symbol, channel, status, message)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(news_id, symbol, channel) DO UPDATE SET
                status=excluded.status,
                message=excluded.message,
                created_at=CURRENT_TIMESTAMP
            """,
            (news_id, symbol, channel, status, message[:4000]),
        )


def fetch_url(url: str) -> str:
    if httpx is not None:
        with httpx.Client(timeout=12, headers={"User-Agent": "CryptoRadar/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    request = Request(url, headers={"User-Agent": "CryptoRadar/1.0"})
    with urlopen(request, timeout=12) as response:  # nosec - configured public RSS URLs only.
        return response.read().decode("utf-8", errors="replace")


def parse_rss_items(xml_text: str, source: str) -> list[NewsItem]:
    root = ElementTree.fromstring(xml_text)
    rows = root.findall(".//item")
    if not rows:
        rows = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    items: list[NewsItem] = []
    for row in rows:
        title = _xml_text(row, "title")
        link = _xml_text(row, "link")
        if not link:
            link_node = row.find("{http://www.w3.org/2005/Atom}link")
            link = str(link_node.attrib.get("href", "")) if link_node is not None else ""
        published_raw = _xml_text(row, "pubDate") or _xml_text(row, "published") or _xml_text(row, "updated")
        published_at = parse_news_datetime(published_raw).isoformat(timespec="seconds")
        summary = _xml_text(row, "description") or _xml_text(row, "summary")
        item_id = stable_news_id(source, title, link)
        if title:
            items.append(NewsItem(item_id, source, html.unescape(strip_tags(title)), link, published_at, html.unescape(strip_tags(summary))))
    return items


def item_to_dict(item: NewsItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "title": item.title,
        "link": item.link,
        "published_at": item.published_at,
        "summary": item.summary,
        "importance_score": 0,
        "sentiment": "neutral",
        "matched_keywords": [],
    }


def score_news_item(item: dict[str, Any], aliases: set[str]) -> dict[str, Any]:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    alias_hits = [alias for alias in aliases if alias and re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", text)]
    if not alias_hits:
        return {**item, "importance_score": 0, "sentiment": "neutral", "matched_keywords": []}
    bullish = _keyword_score(text, BULLISH_KEYWORDS)
    bearish = _keyword_score(text, BEARISH_KEYWORDS)
    base = 45 + min(len(alias_hits), 3) * 8
    importance = min(100, base + bullish["score"] + bearish["score"])
    sentiment = "neutral"
    if bearish["score"] > bullish["score"]:
        sentiment = "bearish"
    elif bullish["score"] > bearish["score"]:
        sentiment = "bullish"
    return {
        **item,
        "importance_score": int(importance),
        "sentiment": sentiment,
        "matched_keywords": sorted(set(bullish["matches"] + bearish["matches"])),
    }


def symbol_aliases(market: dict[str, Any]) -> set[str]:
    symbol = str(market.get("symbol", "")).upper()
    token = market.get("token") or {}
    aliases = {symbol}
    for quote in ("USDT", "FDUSD", "BTC", "ETH", "USDC"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            aliases.add(symbol[: -len(quote)])
    for key in ("symbol", "name", "alphaId", "cexCoinName"):
        value = str(token.get(key) or "").upper().strip()
        if value:
            aliases.add(value)
            aliases.add(value.replace(" ", ""))
    return {alias for alias in aliases if len(alias) >= 2}


def format_preferred_news_alert(market: dict[str, Any], item: dict[str, Any], alert: dict[str, Any]) -> str:
    display = str(market.get("display_symbol") or market.get("symbol"))
    display = display.split(" ", 1)[0]
    trend = trend_label(alert)
    volume = volume_label(alert)
    impact = impact_label(int(item.get("importance_score", 0)))
    why = why_it_matters(item, alert)
    return "\n".join(
        [
            f"📰 {display} — Significant News",
            "",
            f"Impact: {impact}",
            f"Trend: {trend}",
            f"Price Move: {format_pct(alert.get('change_24h'))} 24h",
            f"Volume: {volume}",
            "",
            "Headline:",
            str(item.get("title", "No title")),
            "",
            "Why it matters:",
            why,
            "",
            "🧠 ML breakout:",
            ml_breakout_text(alert),
            "",
            "Source:",
            f"{item.get('source', 'RSS')} - {item.get('link', '')}",
            "",
            "Final:",
            "Analysis-only alert. Not guaranteed profit. Decide manually.",
        ]
    )


def format_no_news_message(market: dict[str, Any], alert: dict[str, Any]) -> str:
    display = str(market.get("display_symbol") or market.get("symbol"))
    display = display.split(" ", 1)[0]
    return "\n".join(
        [
            f"📰 {display} — News Check",
            "",
            "No significant recent public RSS news matched this preferred coin.",
            f"Trend: {trend_label(alert)}",
            f"Price Move: {format_pct(alert.get('change_24h'))} 24h",
            f"Volume: {volume_label(alert)}",
            "",
            "🧠 ML breakout:",
            ml_breakout_text(alert),
            "",
            "Final:",
            "Analysis-only alert. Not guaranteed profit. Decide manually.",
        ]
    )


def trend_label(alert: dict[str, Any]) -> str:
    change = _float(alert.get("change_24h"))
    if change >= 10:
        return "🚀 Huge surge"
    if change >= 2:
        return "📈 Uptrend"
    if change <= -8:
        return "⚠️ Heavy downtrend"
    if change <= -2:
        return "📉 Downtrend"
    return "Neutral"


def volume_label(alert: dict[str, Any]) -> str:
    relative = _float(alert.get("relative_volume"), 1.0)
    prefix = "🔥 " if relative >= 1.5 else ""
    return f"{prefix}{relative:.2f}x normal"


def ml_breakout_text(alert: dict[str, Any]) -> str:
    prediction = alert.get("ml_prediction")
    if not isinstance(prediction, dict) or "success_probability" not in prediction:
        return "collecting enough labeled examples"
    probability = _float(prediction.get("success_probability")) * 100
    risk = _float(prediction.get("risk_score")) * 100
    confidence = _float(prediction.get("confidence_score")) * 100
    data_quality = prediction.get("data_quality", "unknown")
    return f"{probability:.0f}% success probability, risk {risk:.0f}%, confidence {confidence:.0f}%, data {data_quality}"


def why_it_matters(item: dict[str, Any], alert: dict[str, Any]) -> str:
    keywords = item.get("matched_keywords") or []
    sentiment = item.get("sentiment", "neutral")
    parts: list[str] = []
    if keywords:
        parts.append("Matched important terms: " + ", ".join(str(word) for word in keywords[:5]) + ".")
    if sentiment == "bearish":
        parts.append("News tone is risk-focused, so watch downside and volatility.")
    elif sentiment == "bullish":
        parts.append("News tone is constructive, but confirmation still depends on price and volume.")
    if _float(alert.get("change_24h")) >= 10:
        parts.append("Price is already moving strongly, so chase risk is higher.")
    elif _float(alert.get("change_24h")) <= -4:
        parts.append("Price is already weakening, so risk control matters.")
    if _float(alert.get("relative_volume"), 1) >= 1.5:
        parts.append("Volume is elevated versus normal.")
    return " ".join(parts) or "The headline matched this preferred coin and may affect attention or volatility."


def impact_label(score: int) -> str:
    if score >= 85:
        return "High"
    if score >= 70:
        return "Medium-high"
    return "Watch"


def parse_news_datetime(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stable_news_id(source: str, title: str, link: str) -> str:
    digest = hashlib.sha1(f"{source}|{title}|{link}".encode("utf-8")).hexdigest()[:20]
    return f"news-{digest}"


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _xml_text(row: ElementTree.Element, tag: str) -> str:
    direct = row.find(tag)
    if direct is not None and direct.text:
        return direct.text.strip()
    for child in row:
        if child.tag.endswith("}" + tag) and child.text:
            return child.text.strip()
    return ""


def _keyword_score(text: str, keywords: dict[str, int]) -> dict[str, Any]:
    score = 0
    matches: list[str] = []
    for keyword, value in keywords.items():
        if keyword in text:
            score += value
            matches.append(keyword)
    return {"score": score, "matches": matches}


def _age_minutes(created_at: str) -> float:
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 60


def recent_only(items: list[dict[str, Any]], hours: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    kept: list[dict[str, Any]] = []
    for item in items:
        try:
            published = datetime.fromisoformat(str(item["published_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published >= cutoff:
            kept.append(item)
    return kept


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
