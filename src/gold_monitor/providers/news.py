"""Daily gold / macro / geopolitical news via free RSS.

Multi-source → article dedupe → event clustering → relevance filter.
headline_sentiment is keyword-only and must NOT drive causal claims alone.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = "gold-macro-monitor/0.3 (research; +https://github.com/bym0122/gold-macro-monitor)"

# Focused feeds: gold + Fed/official + event-rich geo queries (not bare country names only)
FEEDS = [
    {
        "name": "GN-Gold",
        "url": (
            "https://news.google.com/rss/search?q="
            "gold+price+OR+XAU+OR+%22gold+ETF%22+OR+%22central+bank+gold%22+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "gold",
    },
    {
        "name": "GN-FedMacro",
        "url": (
            "https://news.google.com/rss/search?q="
            "Fed+OR+FOMC+OR+Powell+OR+%22real+yield%22+OR+CPI+OR+PCE+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "us_macro",
    },
    {
        "name": "GN-IranHormuz",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Iran+OR+Hormuz+OR+%22Red+Sea%22+OR+Houthi)+"
            "(attack+OR+strike+OR+sanctions+OR+missile+OR+blockade+OR+escalation+OR+ceasefire+OR+nuclear)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "GN-IsraelGaza",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Israel+OR+Gaza+OR+Lebanon+OR+Hezbollah)+"
            "(attack+OR+strike+OR+ceasefire+OR+missile+OR+escalation+OR+war)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "GN-USIran",
        "url": (
            "https://news.google.com/rss/search?q="
            "(US+OR+United+States+OR+Trump)+Iran+"
            "(strike+OR+attack+OR+sanctions+OR+negotiation+OR+war+OR+military)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "GN-Ukraine",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Ukraine+OR+Russia)+"
            "(attack+OR+strike+OR+missile+OR+escalation+OR+NATO+OR+ceasefire)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
        "tier": 2,
        "default_category": "geopolitics",
    },
    {
        "name": "GN-Taiwan",
        "url": (
            "https://news.google.com/rss/search?q="
            "(Taiwan+OR+%22Taiwan+Strait%22)+"
            "(China+OR+PLA)+(drill+OR+missile+OR+escalation+OR+blockade+OR+tension)+when:2d"
            "&hl=en-US&gl=US&ceid=US:en"
        ),
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
        "name": "BBC-ME",
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

KW_DIRECT = [
    r"\bgold\b", r"\bxau\b", r"\bbullion\b", r"gold etf", r"gold price",
    r"central bank gold", r"gold reserve", r"precious metal",
]
KW_MACRO = [
    r"\bfed\b", r"\bfomc\b", r"\bpowell\b", r"real yield", r"treasury yield",
    r"\bcpi\b", r"\bpce\b", r"inflation", r"\bdxy\b", r"\bus dollar\b",
    r"rate hike", r"rate cut", r"interest rate", r"minutes",
]
KW_GEO = [
    r"\biran\b", r"\bisrael\b", r"\bgaza\b", r"hormuz", r"red sea",
    r"\bhouthi\b", r"\bukraine\b", r"\brussia\b", r"\btaiwan\b",
    r"geopolitic", r"sanction", r"missile", r"airstrike", r"ceasefire",
    r"hezbollah", r"\blebanon\b", r"\bnato\b",
]
KW_SUPPLY = [
    r"gold mine", r"mine supply", r"gold production", r"gold demand",
    r"pboc", r"central bank buy",
]

# Event clustering fingerprints: (event_id, label, patterns, default_gold_bias_hint)
# bias_hint is only a prior for display; final impact comes from market cross-check.
EVENT_PATTERNS: list[tuple[str, str, list[str], str]] = [
    ("E_FED_HAWK", "Fed/政策偏鹰（加息/鹰派信号）",
     [r"rate hike", r"another hike", r"hawkish", r"fed minutes", r"signals? (another )?hike",
      r"higher for longer", r"tighten"], "bearish_prior"),
    ("E_FED_DOVE", "Fed/政策偏鸽（降息/鸽派信号）",
     [r"rate cut", r"dovish", r"easing", r"pause hiking"], "bullish_prior"),
    ("E_GOLD_PRICE", "金价走势/预测类报道",
     [r"gold (price|gains?|falls?|rises?|surges?|drops?|near)", r"xau", r"gold forecast",
      r"gold analysis"], "neutral_prior"),
    ("E_IRAN_HORMUZ", "伊朗/霍尔木兹/红海航运风险",
     [r"hormuz", r"red sea", r"houthi", r"iran.*(attack|strike|war|sanction)",
      r"tanker", r"strait of hormuz"], "bullish_prior"),
    ("E_ISRAEL_GAZA", "以色列/加沙/黎巴嫩冲突",
     [r"gaza", r"israel.*(attack|strike|war)", r"hezbollah", r"lebanon.*(strike|attack)"],
     "bullish_prior"),
    ("E_US_IRAN", "美伊直接对峙/军事/制裁",
     [r"(us|u\.s\.|united states|trump).*iran", r"iran.*(us|u\.s\.|american)",
      r"strike.*iran", r"iran.*sanction"], "bullish_prior"),
    ("E_UKRAINE", "俄乌/北约相关升级",
     [r"ukraine", r"russia.*(missile|attack|strike)", r"nato"], "bullish_prior"),
    ("E_TAIWAN", "台海/中美台紧张",
     [r"taiwan", r"taiwan strait", r"pla.*(drill|exercise)"], "bullish_prior"),
    ("E_INFLATION_DATA", "通胀/就业数据",
     [r"\bcpi\b", r"\bpce\b", r"payroll", r"nonfarm", r"inflation data"], "neutral_prior"),
    ("E_OTHER_GEO", "其他地缘",
     [r"missile", r"airstrike", r"ceasefire", r"sanction", r"escalation"], "neutral_prior"),
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
    headline_sentiment: str = "neutral"  # keyword-only; not causal
    tier: int = 3
    event_id: str = "E_OTHER"
    event_label: str = "未归类"

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
            return raw[:32] if raw else None


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


def _score_relevance(text: str) -> tuple[int, str, list[str]]:
    t = text.lower()
    hits: list[str] = []

    def hit_any(patterns: list[str]) -> bool:
        ok = False
        for p in patterns:
            if re.search(p, t, re.I):
                hits.append(p)
                ok = True
        return ok

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

    bull = len(re.findall(r"safe.?haven|rally|surge|soar|record high|buy gold|inflow", t))
    bear = len(re.findall(r"sell.?off|plunge|slump|outflow|rate hike|stronger dollar|falls? after", t))
    if bull > bear + 1:
        sent = "bullish_headline"
    elif bear > bull + 1:
        sent = "bearish_headline"
    elif bull and bear:
        sent = "mixed_headline"
    else:
        sent = "neutral_headline"

    entities = []
    for tok in ["Fed", "FOMC", "Powell", "Treasury", "Iran", "Israel", "Gaza", "Hormuz",
                "Ukraine", "Russia", "China", "Taiwan", "Houthi", "OPEC", "ECB", "Trump"]:
        if re.search(rf"\b{re.escape(tok)}\b", text, re.I):
            entities.append(tok)
    return score, sent, entities


def _assign_event(text: str) -> tuple[str, str, str]:
    t = text.lower()
    for eid, label, patterns, prior in EVENT_PATTERNS:
        for p in patterns:
            if re.search(p, t, re.I):
                return eid, label, prior
    return "E_OTHER", "其他/未归类", "neutral_prior"


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
        resp = requests.get(feed["url"], timeout=25, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return items

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
        if not title or not url:
            continue
        if pub:
            try:
                pdt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pdt < cutoff:
                    continue
            except Exception:
                pass

        blob = f"{title} {desc}"
        rel, sent, ents = _score_relevance(blob)
        eid, elabel, _prior = _assign_event(blob)
        cat = _categorize(blob, feed.get("default_category", "other"))
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
                headline_sentiment=sent,
                tier=int(feed.get("tier", 3)),
                event_id=eid,
                event_label=elabel,
            )
        )
    return items


def _dedupe_articles(items: list[NewsItem]) -> list[NewsItem]:
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


def cluster_events(items: list[NewsItem]) -> list[dict[str, Any]]:
    """Collapse articles into independent events."""
    buckets: dict[str, list[NewsItem]] = defaultdict(list)
    priors: dict[str, str] = {}
    for it in items:
        buckets[it.event_id].append(it)
        if it.event_id not in priors:
            _, _, prior = _assign_event(it.title)
            priors[it.event_id] = prior

    events: list[dict[str, Any]] = []
    for eid, arts in buckets.items():
        if eid == "E_OTHER" and len(arts) == 1 and arts[0].relevance_to_gold < 4:
            # drop single weak uncategorized
            continue
        arts_sorted = sorted(
            arts,
            key=lambda x: (x.published_at or "",),
        )
        first = arts_sorted[0].published_at
        last = arts_sorted[-1].published_at
        sources = sorted({a.source for a in arts})
        max_rel = max(a.relevance_to_gold for a in arts)
        label = arts[0].event_label
        # Prefer non-generic label
        for a in arts:
            if a.event_id != "E_OTHER":
                label = a.event_label
                break
        events.append(
            {
                "event_id": eid,
                "label": label,
                "article_count": len(arts),
                "source_count": len(sources),
                "sources": sources[:12],
                "first_published_at": first,
                "latest_published_at": last,
                "max_relevance": max_rel,
                "prior_bias": priors.get(eid, "neutral_prior"),
                "sample_titles": [a.title[:120] for a in arts_sorted[:5]],
                "sample_urls": [a.url for a in arts_sorted[:5]],
            }
        )

    # Rank: relevance, then source diversity
    events.sort(key=lambda e: (-e["max_relevance"], -e["source_count"], -e["article_count"]))
    return events


class NewsProvider:
    def fetch_daily(
        self, min_relevance: int = 3, article_limit: int = 40, event_limit: int = 12
    ) -> tuple[list[NewsItem], list[dict[str, Any]]]:
        all_items: list[NewsItem] = []
        for feed in FEEDS:
            all_items.extend(_fetch_feed(feed))
        all_items = _dedupe_articles(all_items)
        filtered = [x for x in all_items if x.relevance_to_gold >= min_relevance]
        filtered.sort(key=lambda x: (-x.relevance_to_gold, x.tier, x.published_at or ""))
        filtered = filtered[:article_limit]
        events = cluster_events(filtered)[:event_limit]
        return filtered, events
