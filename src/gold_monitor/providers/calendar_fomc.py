"""Fed FOMC calendar parser (v0.9)."""
from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
from .calendar_common import CalendarEvent, ET, et_to_iso, make_event_id, status_from_schedule

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
USER_AGENT = "gold-macro-monitor/0.9 (research; +https://github.com/bym0122/gold-macro-monitor)"
BASE = "https://www.federalreserve.gov"
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

def _ymd_et(ymd: str, hour: int = 14, minute: int = 0) -> datetime:
    return datetime(int(ymd[0:4]), int(ymd[4:6]), int(ymd[6:8]), hour, minute, tzinfo=ET)

def _parse_end_day(date_str: str, month_name: str, year: int) -> Optional[str]:
    if not date_str or not month_name:
        return None
    m = MONTH_MAP.get(month_name.strip().lower())
    if not m:
        return None
    cleaned = date_str.replace("*", "").strip()
    if "notation" in cleaned.lower():
        return None
    parts = re.split(r"[-–]", cleaned)
    try:
        day = int(re.sub(r"[^\d]", "", parts[-1]))
    except ValueError:
        return None
    return f"{year:04d}{m:02d}{day:02d}"

def parse_fomc_html(html: str, now: Optional[datetime] = None) -> list[CalendarEvent]:
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []
    seen_s: set[str] = set()
    seen_p: set[str] = set()

    for ymd in sorted(set(re.findall(r"/newsevents/pressreleases/monetary(20\d{6})a\.htm", html))):
        seen_s.add(ymd)
        sched = et_to_iso(_ymd_et(ymd, 14, 0))
        events.append(CalendarEvent(
            event_id=make_event_id("fomc", "statement", ymd),
            event_name="FOMC Statement / Rate Decision", category="fed",
            scheduled_at=sched, timezone="America/New_York",
            status=status_from_schedule(sched, now),
            source_name="Federal Reserve FOMC Calendars",
            source_url=f"{BASE}/newsevents/pressreleases/monetary{ymd}a.htm",
            retrieved_at=retrieved, last_updated_at=retrieved,
            data_quality="official", event_subtype="statement",
        ))

    for ymd in sorted(set(re.findall(r"/monetarypolicy/fomcpres+conf(20\d{6})\.htm", html, re.I))):
        seen_p.add(ymd)
        sched = et_to_iso(_ymd_et(ymd, 14, 30))
        events.append(CalendarEvent(
            event_id=make_event_id("fomc", "press_conference", ymd),
            event_name="FOMC Press Conference", category="fed",
            scheduled_at=sched, timezone="America/New_York",
            status=status_from_schedule(sched, now),
            source_name="Federal Reserve FOMC Calendars",
            source_url=f"{BASE}/monetarypolicy/fomcpresconf{ymd}.htm",
            retrieved_at=retrieved, last_updated_at=retrieved,
            data_quality="official", event_subtype="press_conference",
        ))

    for ymd in sorted(set(re.findall(r"/monetarypolicy/fomcminutes(20\d{6})(?:\.htm|/)", html))):
        approx = _ymd_et(ymd, 14, 0) + timedelta(days=21)
        while approx.weekday() != 2:
            approx += timedelta(days=1)
        sched = et_to_iso(approx.replace(hour=14, minute=0))
        events.append(CalendarEvent(
            event_id=make_event_id("fomc", "minutes", ymd),
            event_name="FOMC Meeting Minutes", category="fed",
            scheduled_at=sched, timezone="America/New_York",
            status=status_from_schedule(sched, now),
            source_name="Federal Reserve FOMC Calendars",
            source_url=f"{BASE}/monetarypolicy/fomcminutes{ymd}.htm",
            retrieved_at=retrieved, last_updated_at=retrieved,
            data_quality="partial", event_subtype="minutes",
            reference_period=f"meeting_end_{ymd}",
        ))

    # FIX: year header is <h4><a id=...>2026 FOMC Meetings</a></h4>
    year_blocks = re.split(
        r"(?i)<h4[^>]*>\s*(?:<a[^>]*>)?\s*(\d{4})\s+FOMC\s+Meetings",
        html,
    )
    i = 1
    while i + 1 < len(year_blocks):
        try:
            year = int(year_blocks[i].strip())
        except ValueError:
            i += 2
            continue
        body = year_blocks[i + 1]
        months = re.findall(
            r"fomc-meeting__month[^>]*>\s*<strong>\s*([A-Za-z]+)\s*</strong>",
            body, flags=re.I,
        )
        dates = re.findall(r"fomc-meeting__date[^>]*>\s*([^<]+)", body, flags=re.I)
        for month_name, date_str in zip(months, dates):
            ymd = _parse_end_day(date_str, month_name, year)
            if not ymd:
                continue
            if ymd not in seen_s:
                seen_s.add(ymd)
                sched = et_to_iso(_ymd_et(ymd, 14, 0))
                events.append(CalendarEvent(
                    event_id=make_event_id("fomc", "statement", ymd),
                    event_name="FOMC Statement / Rate Decision", category="fed",
                    scheduled_at=sched, timezone="America/New_York",
                    status=status_from_schedule(sched, now),
                    source_name="Federal Reserve FOMC Calendars", source_url=FOMC_URL,
                    retrieved_at=retrieved, last_updated_at=retrieved,
                    data_quality="partial", event_subtype="statement",
                    notes=f"Table {month_name} {date_str.strip()} {year}",
                ))
            if ymd not in seen_p:
                seen_p.add(ymd)
                sched = et_to_iso(_ymd_et(ymd, 14, 30))
                events.append(CalendarEvent(
                    event_id=make_event_id("fomc", "press_conference", ymd),
                    event_name="FOMC Press Conference", category="fed",
                    scheduled_at=sched, timezone="America/New_York",
                    status=status_from_schedule(sched, now),
                    source_name="Federal Reserve FOMC Calendars", source_url=FOMC_URL,
                    retrieved_at=retrieved, last_updated_at=retrieved,
                    data_quality="partial", event_subtype="press_conference",
                ))
        i += 2
    return events

class FomcCalendarProvider:
    def fetch(self, window_start=None, window_end=None):
        now = datetime.now(timezone.utc)
        window_start = window_start or (now - timedelta(days=21))
        window_end = window_end or (now + timedelta(days=120))
        try:
            resp = requests.get(FOMC_URL, timeout=30, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            all_ev = parse_fomc_html(resp.text, now=now)
        except Exception as e:
            return [], f"FOMC calendar: {type(e).__name__}: {e}"
        out = []
        for ev in all_ev:
            if not ev.scheduled_at:
                continue
            dt = datetime.fromisoformat(ev.scheduled_at)
            if window_start <= dt.astimezone(timezone.utc) <= window_end:
                out.append(ev)
        return out, None
