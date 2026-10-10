"""Market structure calendar: calculated rules + free official Treasury auctions.

Rules (no external API):
  - month / quarter / year end (calendar dates)
  - US equities quadruple-witching: 3rd Friday of Mar/Jun/Sep/Dec
    (calendar-rule only; not exchange-confirmed holiday-adjusted)

Official free source:
  - Treasury upcoming auctions via FiscalData API (no key)

CME gold futures calendar is attempted; on failure records soft warning only.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

import requests

from gold_monitor.providers.calendar_common import CalendarEvent, make_event_id

USER_AGENT = (
    "gold-macro-monitor/0.9 (research; calendar; "
    "+https://github.com/bym0122/gold-macro-monitor)"
)

TREASURY_UPCOMING_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    "/v1/accounting/od/upcoming_auctions"
)
CME_GOLD_CAL_URL = (
    "https://www.cmegroup.com/markets/metals/precious/gold.calendar.html"
)

FOCUS_TERMS = (
    "2-Year",
    "3-Year",
    "5-Year",
    "7-Year",
    "10-Year",
    "20-Year",
    "30-Year",
    "TIPS",
    "FRN",
    "Note",
    "Bond",
)


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    delta = (4 - first.weekday()) % 7
    first_fri = first + timedelta(days=delta)
    return first_fri + timedelta(days=14)


def _month_end(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


def _iter_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def build_rule_events(
    window_start: date,
    window_end: date,
    now: datetime,
) -> List[CalendarEvent]:
    retrieved = now.isoformat()
    events: List[CalendarEvent] = []

    for y, m in _iter_months(window_start, window_end):
        me = _month_end(y, m)
        if window_start <= me <= window_end:
            is_q = m in (3, 6, 9, 12)
            is_y = m == 12
            if is_y:
                etype, name = "year_end", f"Calendar year-end {y}"
            elif is_q:
                etype, name = "quarter_end", f"Calendar quarter-end {y}-Q{(m // 3)}"
            else:
                etype, name = "month_end_rebalance", f"Calendar month-end {y}-{m:02d}"
            events.append(
                CalendarEvent(
                    event_id=make_event_id("ms", etype, me.isoformat()),
                    event_name=name,
                    category="market_structure",
                    scheduled_at=None,
                    scheduled_date=me.isoformat(),
                    timezone="America/New_York",
                    status="scheduled",
                    source_name="Calendar rule (calculated)",
                    source_url="",
                    retrieved_at=retrieved,
                    last_updated_at=retrieved,
                    data_quality="calculated",
                    notes=(
                        "Natural calendar date only; not adjusted for exchange holidays. "
                        "Not an official rebalance schedule."
                    ),
                    event_type=etype,
                    event_subtype="calculated_rule",
                    time_status="date_only",
                )
            )

        if m in (3, 6, 9, 12):
            qw = _third_friday(y, m)
            if window_start <= qw <= window_end:
                events.append(
                    CalendarEvent(
                        event_id=make_event_id("ms", "quadruple_witching", qw.isoformat()),
                        event_name=f"Quadruple witching (rule) {qw.isoformat()}",
                        category="market_structure",
                        scheduled_at=None,
                        scheduled_date=qw.isoformat(),
                        timezone="America/New_York",
                        status="scheduled",
                        source_name="Calendar rule (3rd Friday Mar/Jun/Sep/Dec)",
                        source_url="",
                        retrieved_at=retrieved,
                        last_updated_at=retrieved,
                        data_quality="calculated",
                        notes=(
                            "US equity index / single-stock / options / futures expiry "
                            "convention (3rd Friday). Not holiday-adjusted; not exchange "
                            "official confirmation. Risk calendar only, not a gold signal."
                        ),
                        event_type="quadruple_witching",
                        event_subtype="calculated_rule",
                        time_status="date_only",
                    )
                )

    return events


def fetch_treasury_upcoming(
    window_start: date,
    window_end: date,
    now: datetime,
) -> Tuple[List[CalendarEvent], Optional[str]]:
    retrieved = now.isoformat()
    params = {
        "filter": f"auction_date:gte:{window_start.isoformat()},auction_date:lte:{window_end.isoformat()}",
        "page[size]": "100",
        "sort": "auction_date",
    }
    try:
        resp = requests.get(
            TREASURY_UPCOMING_URL,
            params=params,
            timeout=30,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        if resp.status_code != 200:
            return [], f"Treasury upcoming_auctions HTTP {resp.status_code}"
        data = resp.json().get("data") or []
    except Exception as e:
        return [], f"Treasury upcoming_auctions: {type(e).__name__}: {e}"

    events: List[CalendarEvent] = []
    for row in data:
        ad = (row.get("auction_date") or "").strip()
        if not ad:
            continue
        stype = (row.get("security_type") or "").strip()
        sterm = (row.get("security_term") or "").strip()
        focus = any(t.lower() in (sterm + " " + stype).lower() for t in FOCUS_TERMS)
        ann = (row.get("announcemt_date") or row.get("announcement_date") or "").strip()
        issue = (row.get("issue_date") or "").strip()
        cusip = (row.get("cusip") or "").strip()
        title = f"Treasury auction: {stype} {sterm}".strip()
        notes_parts = [
            f"auction_date={ad}",
            f"announcement_date={ann or 'n/a'}",
            f"issue_date={issue or 'n/a'}",
        ]
        if cusip:
            notes_parts.append(f"cusip={cusip}")
        if not focus:
            notes_parts.append("bill_or_other")
        events.append(
            CalendarEvent(
                event_id=make_event_id("treasury", stype, sterm, ad, cusip),
                event_name=title,
                category="treasury",
                scheduled_at=None,
                scheduled_date=ad,
                timezone="America/New_York",
                status="scheduled",
                source_name="FiscalData Treasury Upcoming Auctions",
                source_url=TREASURY_UPCOMING_URL,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                notes="; ".join(notes_parts),
                event_type="treasury_auction",
                event_subtype=stype.lower() if stype else "auction",
                time_status="date_only",
                contract=cusip or None,
            )
        )
    return events, None


def fetch_cme_gold_calendar(now: datetime) -> Tuple[List[CalendarEvent], Optional[str]]:
    retrieved = now.isoformat()
    try:
        resp = requests.get(
            CME_GOLD_CAL_URL,
            timeout=20,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        if resp.status_code != 200:
            return [], f"CME gold calendar HTTP {resp.status_code}"
        html = resp.text or ""
        if len(html) < 500:
            return [], "CME gold calendar: empty/short response"
        if "last trade" not in html.lower() and "first notice" not in html.lower():
            return [], (
                "CME gold calendar: page has no static Last Trade/First Notice table "
                "(likely JS-rendered); parse_error"
            )
        events: List[CalendarEvent] = []
        for m in re.finditer(
            r"(GC[FGHJKMNQUVXZ]\d{1,2}|G[FGHJKMNQUVXZ]\d{2})"
            r".{0,80}?(\d{4}-\d{2}-\d{2})",
            html,
            re.I | re.S,
        ):
            code, d = m.group(1).upper(), m.group(2)
            events.append(
                CalendarEvent(
                    event_id=make_event_id("cme", "gold", code, d),
                    event_name=f"CME Gold {code} date marker {d}",
                    category="gold_derivatives",
                    scheduled_at=None,
                    scheduled_date=d,
                    timezone="America/New_York",
                    status="scheduled",
                    source_name="CME Group Gold Calendar (HTML heuristic)",
                    source_url=CME_GOLD_CAL_URL,
                    retrieved_at=retrieved,
                    last_updated_at=retrieved,
                    data_quality="partial",
                    notes=(
                        "Heuristic extract from HTML; field role (LTD/FND/etc.) not verified. "
                        "Do not treat as confirmed official notice date without manual check."
                    ),
                    event_type="gold_futures_date",
                    event_subtype="heuristic",
                    time_status="date_only",
                    contract=code,
                )
            )
        if not events:
            return [], "CME gold calendar: no contract/date pairs parsed (parse_error)"
        return events, None
    except Exception as e:
        return [], f"CME gold calendar: {type(e).__name__}: {e}"


class MarketStructureCalendarProvider:
    """Market-structure + treasury auction calendar."""

    source_name = "market_structure"

    def fetch(
        self,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> Tuple[List[CalendarEvent], Optional[str]]:
        now = datetime.now(timezone.utc)
        ws = (window_start or (now - timedelta(days=7))).date()
        we = (window_end or (now + timedelta(days=90))).date()

        events: List[CalendarEvent] = []
        soft_errors: List[str] = []

        # 1) Always: calculated rules (hard success path)
        events.extend(build_rule_events(ws, we, now))

        # 2) Treasury upcoming (official free) — soft fail
        t_evs, t_err = fetch_treasury_upcoming(ws, we, now)
        if t_err:
            soft_errors.append(t_err)
        else:
            events.extend(t_evs)

        # 3) CME best-effort — soft fail
        c_evs, c_err = fetch_cme_gold_calendar(now)
        if c_err:
            soft_errors.append(c_err)
        else:
            events.extend(c_evs)

        # Soft errors become a status note event; do NOT fail the whole source
        if soft_errors:
            events.append(
                CalendarEvent(
                    event_id=make_event_id("ms", "soft_errors", now.isoformat()[:16]),
                    event_name="Market-structure partial source warnings",
                    category="market_structure",
                    scheduled_at=None,
                    scheduled_date=None,
                    timezone="America/New_York",
                    status="unavailable",
                    source_name="market_structure",
                    source_url="",
                    retrieved_at=now.isoformat(),
                    last_updated_at=now.isoformat(),
                    data_quality="partial",
                    notes="; ".join(soft_errors),
                    event_type="source_status",
                    event_subtype="soft_warning",
                    time_status="unavailable",
                )
            )

        # Rules always produce events in a 90d window → never hard-fail
        return events, None
