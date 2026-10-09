"""Daily gold / macro / geopolitical news via free RSS (no paid API).

Multi-source → dedupe → keyword relevance score → keep high-relevance items.
Does NOT invent summaries beyond RSS title/description snippets.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse

import requests

USER_AGENT = "gold-macro-monitor/0.3 (research; +https://github.com/bym0122/gold-macro-monitor)"

# Google News RSS is the most reliable free multi-topic source; plus official feeds.
FEEDS = [
    {
        "name": "GoogleNews-Gold",
        "url": "https://news.google.com/rss/search?q=gold+price+OR+XAU+OR+%22gold+ETF%22+OR+%22central+bank+gold%22+when:2d&hl=en-US&gl=US&ceid=US:en",
        "tier": 2,
        "default_category": "gold",
    },
    {
        "name": "GoogleNews-FedMacro",
        "url": "https://news.google.com/rss/search?q=Fed+OR+FOMC+OR+Powell+OR+%22real+yield%22+OR+CPI+OR+PCE+OR+%22US+Treasury%22+when:2d&hl=en-US&gl=US&ceid=US:en",
        "tier": 2,
        "default_category": "us_macro",
    },
    {
        "name": "GoogleNews-Geo",
        "url": "https://news.google.com/rss/search?q=Iran+OR+Israel+OR+Gaza+OR+Hormuz+OR+%22Red+Sea%22+OR+Ukraine+OR+Taiwan+when:2d&hl=en-US&gl=US&ceid=US:en",
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "Fed-Press",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "tier": 1,
        "default_category": "us_macro",
    },
    {
        "name": "BBC-MiddleEast",
        "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "AlJazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "tier": 2,
        "default_category": "geopolitics",
    },
]

# Keyword weights for relevance_to_gold (1–5)
KW_DIRECT = [
    r"\bgold\b", r"\bxau\b", r"\bbullion\b", r"gold etf", r"gold price",
    r"central bank gold", r"gold reserve", r"precious metal",
]
KW_MACRO = [
    r"\bfed\b", r"\bfomc\b", r"\bpowell\b", r"real yield", r"treasury yield",
    r"\bcpi\b", r"\bpce\b", r"inflation", r"\bdxy\b", r"\bus dollar\b",
    r"rate hike", r"rate cut", r"interest rate",
]
KW_GEO = [
    r"\biran\b", r"\bisrael\b", r"\bgaza\b", r"hormuz", r"red sea",
    r"\bhouthi\b", r"\bukraine\b", r"\brussia\b", r"\btaiwan\b",
    r"geopolitic", r"sanction", r"missile", r"airstrike",
]
KW_SUPPLY = [
    r"gold mine", r"mine supply", r"gold production", r"gold demand",
    r"pboc", r"people's bank", r"central bank buy",
]


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published_at: Optional[str]
    fetched_at: str
    category: str
    summary: str
    entities: list[str] = field(default_factory=list)
    relevance_to_gold: int = 1
    sentiment: str = "neutral"  # bullish_gold | bearish_gold | neutral | mixed
    tier: int = 3  # 1 official > 2 major > 3 other

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        # try ISO
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return raw[:32] if raw else None


def _local(tag: str, el: ET.Element) -> Optional[ET.Element]:
    # handle default namespaces loosely
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


def _score_relevance(text: str) -> tuple[int, str, list[str]]:
    t = text.lower()
    hits: list[str] = []
    score = 1

    def hit_any(patterns: list[str]) -> bool:
        for p in patterns:
            if re.search(p, t, re.I):
                hits.append(p)
                return True
        return False

    direct = hit_any(KW_DIRECT)
    macro = hit_any(KW_MACRO)
    geo = hit_any(KW_GEO)
    supply = hit_any(KW_SUPPLY)

    if direct and (macro or geo or supply):
        score = 5
    elif direct:
        score = 4
    elif geo and macro:
        score = 4
    elif geo or (macro and supply):
        score = 3
    elif macro or supply:
        score = 3
    else:
        score = 1

    # crude sentiment toward gold
    bull = len(re.findall(r"safe.?haven|rally|surge|soar|record high|buy gold|inflow", t))
    bear = len(re.findall(r"sell.?off|plunge|slump|outflow|rate hike|stronger dollar", t))
    if bull > bear + 1:
        sent = "bullish_gold"
    elif bear > bull + 1:
        sent = "bearish_gold"
    elif bull and bear:
        sent = "mixed"
    else:
        sent = "neutral"

    # entities: simple capitalised / known tokens
    entities = []
    for tok in ["Fed", "FOMC", "Powell", "Treasury", "Iran", "Israel", "Gaza", "Hormuz",
                "Ukraine", "Russia", "China", "Taiwan", "Houthi", "OPEC", "ECB"]:
        if re.search(rf"\b{re.escape(tok)}\b", text, re.I):
            entities.append(tok)
    return score, sent, entities


def _categorize(text: str, default: str) -> str:
    t = text.lower()
    if any(re.search(p, t) for p in KW_DIRECT + KW_SUPPLY):
        if any(re.search(p, t) for p in KW_GEO):
            return "gold_geo"
        return "gold"
    if any(re.search(p, t) for p in KW_GEO):
        return "geopolitics"
    if any(re.search(p, t) for p in KW_MACRO):
        return "us_macro"
    return default


def _fetch_feed(feed: dict) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    items: list[NewsItem] = []
    try:
        resp = requests.get(
            feed["url"],
            timeout=25,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return items

    # RSS 2.0 item or Atom entry
    channel_items = root.findall(".//item")
    if not channel_items:
        channel_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        channel_items += root.findall(".//entry")

    cutoff = now - timedelta(hours=36)

    for el in channel_items:
        title = _strip_html(_text(_local("title", el)))
        link_el = _local("link", el)
        url = _text(link_el)
        if not url and link_el is not None:
            url = link_el.get("href") or ""
        # Google News sometimes nests
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
            or _text(_local("date", el))
        )
        if not title or not url:
            continue
        # age filter when parseable
        if pub:
            try:
                pdt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pdt < cutoff:
                    continue
            except Exception:
                pass

        blob = f"{title} {desc}"
        rel, sent, ents = _score_relevance(blob)
        cat = _categorize(blob, feed.get("default_category", "other"))
        # source hostname as display source when possible
        host = urlparse(url).netloc or feed["name"]
        items.append(
            NewsItem(
                title=title[:300],
                source=host.replace("www.", ""),
                url=url,
                published_at=pub,
                fetched_at=fetched_at,
                category=cat,
                summary=(desc[:280] + ("…" if len(desc) > 280 else "")),
                entities=ents,
                relevance_to_gold=rel,
                sentiment=sent,
                tier=int(feed.get("tier", 3)),
            )
        )
    return items


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        u = it.url.split("?")[0].lower()
        tnorm = re.sub(r"\W+", "", it.title.lower())[:80]
        if u in seen_url or tnorm in seen_title:
            continue
        seen_url.add(u)
        seen_title.add(tnorm)
        out.append(it)
    return out


class NewsProvider:
    def fetch_daily(self, min_relevance: int = 3, limit: int = 25) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        for feed in FEEDS:
            all_items.extend(_fetch_feed(feed))
        all_items = _dedupe(all_items)
        # rank: relevance desc, tier asc (official first), published desc
        def sort_key(x: NewsItem):
            return (-x.relevance_to_gold, x.tier, x.published_at or "")

        ranked = sorted(all_items, key=sort_key)
        filtered = [x for x in ranked if x.relevance_to_gold >= min_relevance]
        return filtered[:limit]
