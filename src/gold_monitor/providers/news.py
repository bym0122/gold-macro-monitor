"""News collection & deterministic dedupe only (v0.7).

- Default lookback: 24 hours
- Per-feed cap with explicit possible_truncation / feed_hit_cap flag
- No semantic clustering, no gold-direction inference
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
]

GOLD_KEYWORDS = [
    "gold", "xau", "bullion", "etf", "central bank", "reserve",
    "fed", "fomc", "powell", "yield", "real yield", "tips",
    "cpi", "pce", "inflation", "dollar", "dxy", "treasury",
    "nfp", "payroll", "employment", "unemployment", "ppi",
    "iran", "hormuz", "sanctions", "strike",
]


def _article_id(url: str, title: str) -> str:
    key = (url or "").strip().lower() + "|" + re.sub(r"\W+", "", (title or "").lower())[:80]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _is_google_news_url(url: str) -> bool:
    return "news.google.com" in (url or "")


def _extract_source_from_title(title: str) -> tuple[str, Optional[str]]:
    m = re.search(r"\s+-\s+([^-]+)$", title or "")
    if m:
        src = m.group(1).strip()
        clean = (title or "")[: m.start()].strip()
        return clean, src
    return title or "", None


def _rule_relevance(text: str) -> int:
    t = (text or "").lower()
    return min(sum(1 for k in GOLD_KEYWORDS if k in t), 10)


def _real_summary(desc: str, title: str) -> tuple[Optional[str], str]:
    d = re.sub(r"<[^>]+>", " ", desc or "")
    d = re.sub(r"\s+", " ", d).strip()
    t = (title or "").strip()
    if not d or d == t:
        return None, "title_only"
    return d, "rss_summary_only"


def _norm_url(url: str) -> str:
    try:
        p = urlparse(url or "")
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
    except Exception:
        return (url or "").strip()


@dataclass
class NewsArticle:
    article_id: str
    title: str
    source_name: Optional[str]
    source_feed: str
    original_url: str
    url_is_google_news_redirect: bool
    published_at: Optional[str]
    fetched_at: str
    summary: Optional[str]
    language: str
    search_topic: str
    keyword_tags: list[str] = field(default_factory=list)
    relevance_to_gold_rule_score: Optional[int] = None
    headline_sentiment: str = "neutral"
    content_status: str = "title_only"
    possible_duplicate: bool = False
    feed_hit_cap: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deterministic_dedupe(articles: list[NewsArticle]) -> tuple[list[NewsArticle], int]:
    """Keep distinct URLs; same URL drops later copies. Different URLs kept even if similar title."""
    seen_url: set[str] = set()
    out: list[NewsArticle] = []
    dropped = 0
    for a in articles:
        nu = _norm_url(a.original_url)
        if nu and nu in seen_url:
            dropped += 1
            a.possible_duplicate = True
            continue
        if nu:
            seen_url.add(nu)
        out.append(a)
    return out, dropped


@dataclass
class NewsCollectionResult:
    articles: list[NewsArticle]
    stats: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "news_v1",
            "articles": [a.to_dict() for a in self.articles],
            "stats": self.stats,
        }


class NewsProvider:
    def __init__(
        self,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        per_feed_cap: int = DEFAULT_PER_FEED_CAP,
    ):
        self.lookback_hours = lookback_hours
        self.per_feed_cap = per_feed_cap

    def collect(self) -> NewsCollectionResult:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.lookback_hours)
        fetched_at = now.isoformat()
        raw: list[NewsArticle] = []
        feed_stats: list[dict[str, Any]] = []

        for feed in FEEDS:
            name = feed["name"]
            topic = feed.get("search_topic") or name
            items: list[NewsArticle] = []
            truncated = False
            error = None
            try:
                resp = requests.get(
                    feed["url"], timeout=25, headers={"User-Agent": USER_AGENT}
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                entries = (
                    list(channel.findall("item"))
                    if channel is not None
                    else list(root.findall(".//item"))
                )
                if len(entries) >= self.per_feed_cap:
                    truncated = True
                for entry in entries[: self.per_feed_cap]:
                    title_raw = (entry.findtext("title") or "").strip()
                    title, src_from_title = _extract_source_from_title(title_raw)
                    link = (entry.findtext("link") or "").strip()
                    desc = (entry.findtext("description") or "").strip()
                    summary, status = _real_summary(desc, title)
                    pub_raw = entry.findtext("pubDate")
                    pub_iso = None
                    if pub_raw:
                        try:
                            dt = parsedate_to_datetime(pub_raw)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            dt = dt.astimezone(timezone.utc)
                            if dt < cutoff:
                                continue
                            pub_iso = dt.isoformat()
                        except Exception:
                            pass
                    source_el = entry.find("source")
                    source_name = (
                        (source_el.text or "").strip() if source_el is not None else ""
                    ) or src_from_title
                    text_for_score = f"{title} {summary or ''}"
                    art = NewsArticle(
                        article_id=_article_id(link, title),
                        title=title,
                        source_name=source_name or None,
                        source_feed=name,
                        original_url=link,
                        url_is_google_news_redirect=_is_google_news_url(link),
                        published_at=pub_iso,
                        fetched_at=fetched_at,
                        summary=summary,
                        language="en",
                        search_topic=topic,
                        keyword_tags=[k for k in GOLD_KEYWORDS if k in text_for_score.lower()][:12],
                        relevance_to_gold_rule_score=_rule_relevance(text_for_score),
                        content_status=status,
                        feed_hit_cap=truncated,
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
            raw.extend(items)

        deduped, dropped = deterministic_dedupe(raw)
        known = sorted(
            [a for a in deduped if a.published_at],
            key=lambda a: a.published_at or "",
            reverse=True,
        )
        unknown = [a for a in deduped if not a.published_at]
        ordered = known + unknown

        stats = {
            "lookback_hours": self.lookback_hours,
            "per_feed_cap": self.per_feed_cap,
            "feeds": feed_stats,
            "raw_count": len(raw),
            "after_deterministic_dedupe": len(ordered),
            "duplicates_dropped": dropped,
            "possible_truncation_any": any(s.get("possible_truncation") for s in feed_stats),
            "fetched_at_utc": fetched_at,
        }
        return NewsCollectionResult(articles=ordered, stats=stats)
