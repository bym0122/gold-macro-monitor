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

USER_AGENT = "gold-macro-monitor/0.7 (data-collection; +https://github.com/bym0122/gold-macro-monitor)"

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
        "name": "GN-IranHormuz",
        "search_topic": "iran_hormuz_red_sea",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Iran+OR+Hormuz+OR+%22Red+Sea%22+OR+Houthi)+"
            "(attack+OR+strike+OR+sanctions+OR+missile+OR+blockade+OR+escalation+OR+ceasefire+OR+nuclear)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-IsraelGaza",
        "search_topic": "israel_gaza_lebanon",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Israel+OR+Gaza+OR+Lebanon+OR+Hezbollah)+"
            "(attack+OR+strike+OR+ceasefire+OR+missile+OR+escalation+OR+war)+when:1d"
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
        "name": "GN-Ukraine",
        "search_topic": "russia_ukraine",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Ukraine+OR+Russia)+"
            "(attack+OR+strike+OR+missile+OR+escalation+OR+NATO+OR+ceasefire+OR+sanctions)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GN-Taiwan",
        "search_topic": "china_taiwan",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Taiwan+OR+%22Taiwan+Strait%22)+"
            "(China+OR+PLA)+(drill+OR+missile+OR+escalation+OR+blockade+OR+tension)+when:1d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "Fed-Press",
        "search_topic": "fed_official",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
    },
    {
        "name": "BBC-ME",
        "search_topic": "middle_east_bbc",
        "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    },
    {
        "name": "AlJazeera",
        "search_topic": "middle_east_aljazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
    },
]

TAG_PATTERNS: list[tuple[str, str]] = [
    ("gold", r"\bgold\b|\bxau\b|bullion|gold etf"),
    ("fed", r"\bfed\b|\bfomc\b|\bpowell\b"),
    ("yields", r"yield|treasury|real yield"),
    ("inflation", r"\bcpi\b|\bpce\b|inflation"),
    ("dollar", r"\bdxy\b|us dollar|greenback"),
    ("iran", r"\biran\b|hormuz"),
    ("israel_gaza", r"\bisrael\b|\bgaza\b|hezbollah|\blebanon\b"),
    ("ukraine", r"\bukraine\b|\brussia\b|\bnato\b"),
    ("taiwan", r"\btaiwan\b"),
    ("red_sea", r"red sea|\bhouthi\b"),
    ("sanctions", r"sanction"),
    ("military", r"missile|airstrike|attack|strike|ceasefire"),
]


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
    summary: Optional[str]  # None if no real RSS description
    language: Optional[str]
    search_topic: str
    keyword_tags: list[str] = field(default_factory=list)
    relevance_to_gold_rule_score: Optional[int] = None
    relevance_score_note: str = "machine keyword rule score; not impact judgment"
    headline_sentiment: Optional[str] = None
    content_status: str = "title_only"  # title_only | rss_summary_only | full_text_available | fetch_failed
    possible_duplicate: bool = False
    feed_hit_cap: bool = False  # this article came from a feed that hit per-feed cap

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None


def _local(tag: str, el: ET.Element) -> Optional[ET.Element]:
    if el.find(tag) is not None:
        return el.find(tag)
    for child in el:
        if child.tag.endswith(tag) or child.tag == tag:
            return child
    return None


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _article_id(url: str, title: str) -> str:
    key = (url or "").strip().lower() + "|" + re.sub(r"\W+", "", (title or "").lower())[:80]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _norm_url(url: str) -> str:
    return (url or "").strip().split("#")[0].rstrip("/")


def _norm_title(title: str) -> str:
    return re.sub(r"\W+", "", (title or "").lower())[:100]


def _extract_source_from_title(title: str) -> tuple[str, Optional[str]]:
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts) == 2 and 1 < len(parts[1]) < 80:
            return parts[0].strip(), parts[1].strip()
    return title, None


def _is_google_news_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "news.google." in host


def _keyword_tags(text: str) -> list[str]:
    t = text.lower()
    tags = []
    for name, pat in TAG_PATTERNS:
        if re.search(pat, t, re.I):
            tags.append(name)
    return tags


def _rule_relevance(text: str) -> int:
    t = text.lower()
    score = 1
    if re.search(r"\bgold\b|\bxau\b|bullion|gold etf", t):
        score = 4
    if re.search(r"\bfed\b|\bfomc\b|yield|\bcpi\b|\bdxy\b", t):
        score = max(score, 3)
    if re.search(r"\biran\b|hormuz|\bgaza\b|\bukraine\b|\btaiwan\b|houthi", t):
        score = max(score, 3)
    if score >= 4 and re.search(r"\biran\b|hormuz|\bfed\b|yield", t):
        score = 5
    return score


def _headline_sentiment_kw(text: str) -> str:
    t = text.lower()
    bull = len(re.findall(r"safe.?haven|rally|surge|soar|record high", t))
    bear = len(re.findall(r"sell.?off|plunge|slump|falls? after", t))
    if bull > bear + 1:
        return "bullish_headline_kw"
    if bear > bull + 1:
        return "bearish_headline_kw"
    if bull and bear:
        return "mixed_headline_kw"
    return "neutral_headline_kw"


def _real_summary(desc: str, title: str) -> tuple[Optional[str], str]:
    """Return (summary_or_None, content_status). Never paste title as fake summary."""
    d = (desc or "").strip()
    if not d:
        return None, "title_only"
    # If description is essentially the title, treat as title_only
    if _norm_title(d) == _norm_title(title) or d.lower() == title.lower():
        return None, "title_only"
    return (d[:500] + ("…" if len(d) > 500 else "")), "rss_summary_only"


def _fetch_feed(
    feed: dict[str, Any],
    lookback_hours: int,
    per_feed_cap: int,
) -> tuple[list[NewsArticle], Optional[str], bool]:
    """Returns (articles, error_or_None, hit_cap)."""
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    items: list[NewsArticle] = []
    try:
        resp = requests.get(feed["url"], timeout=25, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        return [], f"{feed['name']}: {type(e).__name__}: {e}", False

    channel_items = root.findall(".//item")
    if not channel_items:
        channel_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        channel_items += root.findall(".//entry")

    total_in_feed = len(channel_items)
    cutoff = now - timedelta(hours=lookback_hours)
    count = 0
    hit_cap = False

    for el in channel_items:
        if count >= per_feed_cap:
            hit_cap = True
            break
        title_raw = _strip_html(_text(_local("title", el)))
        link_el = _local("link", el)
        url = _text(link_el)
        if not url and link_el is not None:
            url = link_el.get("href") or ""
        if not url:
            for child in el:
                if child.tag.endswith("link") or child.tag == "link":
                    url = (child.text or child.get("href") or "").strip()
                    if url:
                        break
        desc = _strip_html(
            _text(_local("description", el))
            or _text(_local("summary", el))
            or _text(_local("content", el))
        )
        pub = _parse_date(
            _text(_local("pubDate", el))
            or _text(_local("published", el))
            or _text(_local("updated", el))
        )
        if not title_raw or not url:
            continue

        if pub:
            try:
                pdt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pdt < cutoff:
                    continue
            except Exception:
                pass

        title, src_from_title = _extract_source_from_title(title_raw)
        is_gn = _is_google_news_url(url)
        source_name = src_from_title
        if not source_name and not is_gn:
            host = urlparse(url).netloc.replace("www.", "")
            source_name = host or None
        if not source_name:
            source_name = None

        src_el = _local("source", el)
        if src_el is not None:
            sname = _text(src_el) or src_el.get("url")
            if sname:
                source_name = sname.strip()

        summary, cstatus = _real_summary(desc, title)
        blob = f"{title} {summary or ''}"
        art = NewsArticle(
            article_id=_article_id(url, title),
            title=title[:400],
            source_name=source_name,
            source_feed=feed["name"],
            original_url=url,
            url_is_google_news_redirect=is_gn,
            published_at=pub,
            fetched_at=fetched_at,
            summary=summary,
            language="en",
            search_topic=feed.get("search_topic") or feed["name"],
            keyword_tags=_keyword_tags(blob),
            relevance_to_gold_rule_score=_rule_relevance(blob),
            headline_sentiment=_headline_sentiment_kw(blob),
            content_status=cstatus,
            feed_hit_cap=False,  # set after loop if hit
        )
        items.append(art)
        count += 1

    # Cap hit: more items in feed XML than we took (after time filter we may still hit)
    if count >= per_feed_cap and total_in_feed > per_feed_cap:
        hit_cap = True
    if hit_cap:
        for a in items:
            a.feed_hit_cap = True

    return items, None, hit_cap


def deterministic_dedupe(articles: list[NewsArticle]) -> tuple[list[NewsArticle], int]:
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    out: list[NewsArticle] = []
    dropped = 0
    for a in articles:
        nu = _norm_url(a.original_url).lower()
        nt = _norm_title(a.title)
        if nu in seen_url:
            dropped += 1
            continue
        if nt and nt in seen_title:
            a.possible_duplicate = True
            out.append(a)
            seen_url.add(nu)
            continue
        seen_url.add(nu)
        if nt:
            seen_title.add(nt)
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
            "collection_stats": self.stats,
        }


class NewsProvider:
    def collect(
        self,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        per_feed_cap: int = DEFAULT_PER_FEED_CAP,
    ) -> NewsCollectionResult:
        raw: list[NewsArticle] = []
        failed_feeds: list[str] = []
        per_feed_counts: dict[str, int] = {}
        per_topic_counts: dict[str, int] = {}
        truncated_feeds: list[str] = []

        for feed in FEEDS:
            arts, err, hit_cap = _fetch_feed(feed, lookback_hours, per_feed_cap)
            if err:
                failed_feeds.append(err)
            if hit_cap:
                truncated_feeds.append(feed["name"])
            per_feed_counts[feed["name"]] = len(arts)
            topic = feed.get("search_topic") or feed["name"]
            per_topic_counts[topic] = per_topic_counts.get(topic, 0) + len(arts)
            raw.extend(arts)

        total_raw = len(raw)
        deduped, dropped = deterministic_dedupe(raw)

        known = [a for a in deduped if a.published_at]
        unknown = [a for a in deduped if not a.published_at]
        known.sort(key=lambda a: a.published_at or "", reverse=True)
        ordered = known + unknown

        unknown_source = sum(1 for a in ordered if not a.source_name)
        gn_redirect = sum(1 for a in ordered if a.url_is_google_news_redirect)
        rss_only = sum(1 for a in ordered if a.content_status == "rss_summary_only")
        title_only = sum(1 for a in ordered if a.content_status == "title_only")

        stats = {
            "lookback_hours": lookback_hours,
            "per_feed_cap": per_feed_cap,
            "raw_fetched": total_raw,
            "after_deterministic_dedupe": len(ordered),
            "exact_dupes_dropped": dropped,
            "full_text_available": 0,
            "rss_summary_only": rss_only,
            "title_only": title_only,
            "unknown_source_name": unknown_source,
            "google_news_redirect_urls": gn_redirect,
            "per_feed_counts": per_feed_counts,
            "per_topic_counts": per_topic_counts,
            "failed_feeds": failed_feeds,
            "possibly_truncated_feeds": truncated_feeds,
            "possible_truncation": len(truncated_feeds) > 0,
            "truncation_note": (
                "One or more feeds hit per_feed_cap; Google News RSS has no reliable free pagination. "
                "Items beyond the cap were not fetched."
                if truncated_feeds
                else None
            ),
            "note": (
                "Collection coverage stats only. Not event counts. No semantic clustering. "
                f"Lookback={lookback_hours}h."
            ),
        }
        return NewsCollectionResult(articles=ordered, stats=stats)
