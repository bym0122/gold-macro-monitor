"""News collection & deterministic dedupe only (v0.7).

- Default lookback: 24 hours
- Per-feed cap with explicit possible_truncation flag
- No semantic clustering, no gold-direction inference
- Do not drop articles for missing gold keywords or empty body
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = "gold-macro-monitor/0.8 (data-collection; +https://github.com/bym0122/gold-macro-monitor)"

DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_PER_FEED_CAP = 80

FEEDS: list[dict[str, Any]] = [
    {
        "name": "GN-Gold",
        "search_topic": "gold_etf_central_banks",
        "url": (
            "https://news.google.com/rss/search?q="
            "gold+price+OR+XAU+OR+%22gold+ETF%22+OR+%22central+bank+gold%22+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-FedMacro",
        "search_topic": "fed_macro_yields_dollar",
        "url": (
            "https://news.google.com/rss/search?q="
            "Fed+OR+FOMC+OR+Powell+OR+%22real+yield%22+OR+CPI+OR+PCE+OR+Treasury+OR+DXY+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-NFP",
        "search_topic": "us_nfp_employment",
        "url": (
            "https://news.google.com/rss/search?q="
            "%22nonfarm+payrolls%22+OR+NFP+OR+%22Employment+Situation%22+OR+%22average+hourly+earnings%22+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-CPI-PPI",
        "search_topic": "us_cpi_ppi",
        "url": (
            "https://news.google.com/rss/search?q="
            "%22Consumer+Price+Index%22+OR+%22Core+CPI%22+OR+%22Producer+Price+Index%22+OR+%22Core+PPI%22+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-PCE-FOMC",
        "search_topic": "us_pce_fomc",
        "url": (
            "https://news.google.com/rss/search?q="
            "%22Personal+Consumption%22+OR+%22Core+PCE%22+OR+%22FOMC+minutes%22+OR+%22Fed+rate+decision%22+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-IranHormuz",
        "search_topic": "iran_hormuz_red_sea",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Iran+OR+Hormuz+OR+%22Red+Sea%22)+(%22oil+price%22+OR+shipping+OR+tanker+OR+Houthi)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-IsraelGaza",
        "search_topic": "israel_gaza_lebanon",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Israel+OR+Gaza+OR+Hezbollah+OR+Lebanon)+(ceasefire+OR+escalation+OR+war)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-USIran",
        "search_topic": "us_iran",
        "url": (
            "https://news.google.com/rss/search?q="
            "(US+OR+United+States+OR+Trump)+Iran+"
            "(strike+OR+attack+OR+sanctions+OR+negotiation+OR+war+OR+military)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-RussiaUkraine",
        "search_topic": "russia_ukraine",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Russia+OR+Ukraine)+(war+OR+offensive+OR+ceasefire+OR+NATO)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-ChinaTaiwan",
        "search_topic": "china_taiwan",
        "url": (
            "https://news.google.com/rss/search?q="
            "(China+OR+Taiwan)+(military+OR+exercise+OR+strait+OR+invasion+OR+tensions)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
]

# Keyword tags for rule scoring only (not direction)
GOLD_KEYWORDS = [
    "gold", "xau", "bullion", "etf", "central bank", "reserve",
    "fed", "fomc", "powell", "yield", "real yield", "tips",
    "cpi", "pce", "inflation", "dollar", "dxy", "treasury",
    "nfp", "payroll", "employment", "unemployment",
    "ppi", "producer price",
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_pub_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
    except Exception:
        return (url or "").strip()


def _is_google_news_redirect(url: str) -> bool:
    return "news.google.com" in (url or "")


def _article_id(title: str, url: str) -> str:
    key = f"{(title or '').strip().lower()}|{_normalize_url(url)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _rule_score(title: str, summary: str) -> int:
    text = f"{title or ''} {summary or ''}".lower()
    hits = sum(1 for k in GOLD_KEYWORDS if k in text)
    return min(hits, 10)


def _keyword_tags(title: str, summary: str) -> list[str]:
    text = f"{title or ''} {summary or ''}".lower()
    return [k for k in GOLD_KEYWORDS if k in text][:12]


@dataclass
class NewsArticle:
    article_id: str
    title: str
    source_name: str
    source_feed: str
    original_url: str
    url_is_google_news_redirect: bool
    published_at: Optional[str]
    fetched_at: str
    summary: Optional[str]
    language: str
    search_topic: str
    keyword_tags: list[str] = field(default_factory=list)
    relevance_to_gold_rule_score: int = 0
    headline_sentiment: str = "neutral"
    content_status: str = "summary_only"
    possible_duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NewsCollectionResult:
    articles: list[NewsArticle]
    stats: dict[str, Any]


class NewsProvider:
    def __init__(
        self,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        per_feed_cap: int = DEFAULT_PER_FEED_CAP,
    ):
        self.lookback_hours = lookback_hours
        self.per_feed_cap = per_feed_cap

    def collect(self) -> NewsCollectionResult:
        now = _now_utc()
        cutoff = now - timedelta(hours=self.lookback_hours)
        fetched_at = now.isoformat()
        all_items: list[NewsArticle] = []
        feed_stats: list[dict[str, Any]] = []

        for feed in FEEDS:
            name = feed["name"]
            topic = feed.get("search_topic") or name
            url = feed["url"]
            items: list[NewsArticle] = []
            truncated = False
            error = None
            try:
                resp = requests.get(
                    url,
                    timeout=25,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                entries = list(channel.findall("item")) if channel is not None else list(root.findall(".//item"))
                if len(entries) >= self.per_feed_cap:
                    truncated = True
                for entry in entries[: self.per_feed_cap]:
                    title = (entry.findtext("title") or "").strip()
                    link = (entry.findtext("link") or "").strip()
                    summary = (entry.findtext("description") or "").strip()
                    # strip simple HTML
                    summary = re.sub(r"<[^>]+>", " ", summary)
                    summary = re.sub(r"\s+", " ", summary).strip() or None
                    pub_raw = entry.findtext("pubDate")
                    pub_dt = _parse_pub_date(pub_raw)
                    if pub_dt and pub_dt < cutoff:
                        continue
                    source_el = entry.find("source")
                    source_name = (source_el.text or "").strip() if source_el is not None else ""
                    if not source_name:
                        source_name = name
                    art = NewsArticle(
                        article_id=_article_id(title, link),
                        title=title,
                        source_name=source_name,
                        source_feed=name,
                        original_url=link,
                        url_is_google_news_redirect=_is_google_news_redirect(link),
                        published_at=pub_dt.isoformat() if pub_dt else None,
                        fetched_at=fetched_at,
                        summary=summary,
                        language="en",
                        search_topic=topic,
                        keyword_tags=_keyword_tags(title, summary or ""),
                        relevance_to_gold_rule_score=_rule_score(title, summary or ""),
                        content_status="summary_only",
                    )
                    items.append(art)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

            feed_stats.append(
                {
                    "feed": name,
                    "search_topic": topic,
                    "fetched": len(items),
                    "possible_truncation": truncated,
                    "error": error,
                }
            )
            all_items.extend(items)

        # Deterministic dedupe by normalized URL then title
        by_url: dict[str, NewsArticle] = {}
        by_title: dict[str, NewsArticle] = {}
        ordered: list[NewsArticle] = []
        for a in all_items:
            nu = _normalize_url(a.original_url)
            nt = re.sub(r"\s+", " ", (a.title or "").lower()).strip()
            if nu and nu in by_url:
                a.possible_duplicate = True
                continue
            if nt and nt in by_title:
                a.possible_duplicate = True
                continue
            if nu:
                by_url[nu] = a
            if nt:
                by_title[nt] = a
            ordered.append(a)

        # Sort: known published_at desc, then unknown
        def sort_key(x: NewsArticle):
            return (x.published_at or "", x.title or "")

        known = sorted([a for a in ordered if a.published_at], key=sort_key, reverse=True)
        unknown = [a for a in ordered if not a.published_at]
        ordered = known + unknown

        stats = {
            "lookback_hours": self.lookback_hours,
            "per_feed_cap": self.per_feed_cap,
            "feeds": feed_stats,
            "raw_count": len(all_items),
            "deduped_count": len(ordered),
            "possible_truncation_any": any(s.get("possible_truncation") for s in feed_stats),
            "fetched_at_utc": fetched_at,
        }
        return NewsCollectionResult(articles=ordered, stats=stats)
