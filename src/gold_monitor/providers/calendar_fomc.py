"""Fed FOMC calendar parser (v0.9) — future meetings from official table, no invented times."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from .calendar_common import (
    CalendarEvent,
    ET,
    et_to_iso,
    make_event_id,
    status_from_schedule,
)

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
USER_AGENT = (
    "gold-macro-monitor/0.9 (research; +https://github.com/bym0122/gold-macro-monitor)"
)
BASE = "https://www.federalreserve.gov"
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _ymd_et(ymd: str, hour: int = 14, minute: int = 0) -> datetime:
    return datetime(int(ymd[0:4]), int(ymd[4:6]), int(ymd[6:8]), hour, minute, tzinfo=ET)


def _parse_end_day(date_str: str, month_name: str, year: int) -> Optional[str]:
    """Parse '27-28' or '27-28*' or '8-9*' → YYYYMMDD (meeting end day)."""
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
    """Parse FOMC calendars page.

    - Released statement / press-conf / minutes links → exact date, time known for past.
    - Future meeting table (month + date range) → scheduled_date only, scheduled_at=None,
      time_status=unverified. Never invent 14:00/14:30 for future meetings.
    """
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []
    seen_s: set[str] = set()
    seen_p: set[str] = set()

    # --- Released materials (have concrete HTML links) ---
    for ymd in sorted(set(re.findall(r"/newsevents/pressreleases/monetary(20\d{6})a\.htm", html))):
        seen_s.add(ymd)
        sched = et_to_iso(_ymd_et(ymd, 14, 0))
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "statement", ymd),
                event_name="FOMC Statement / Rate Decision",
                category="fed",
                scheduled_at=sched,
                timezone="America/New_York",
                status=status_from_schedule(sched, now),
                source_name="Federal Reserve FOMC Calendars",
                source_url=f"{BASE}/newsevents/pressreleases/monetary{ymd}a.htm",
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                event_subtype="statement",
                scheduled_date=f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}",
                time_status="verified",
            )
        )

    for ymd in sorted(set(re.findall(r"/monetarypolicy/fomcpres+conf(20\d{6})\.htm", html, re.I))):
        seen_p.add(ymd)
        sched = et_to_iso(_ymd_et(ymd, 14, 30))
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "press_conference", ymd),
                event_name="FOMC Press Conference",
                category="fed",
                scheduled_at=sched,
                timezone="America/New_York",
                status=status_from_schedule(sched, now),
                source_name="Federal Reserve FOMC Calendars",
                source_url=f"{BASE}/monetarypolicy/fomcpresconf{ymd}.htm",
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                event_subtype="press_conference",
                scheduled_date=f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}",
                time_status="verified",
            )
        )

    for ymd in sorted(set(re.findall(r"/monetarypolicy/fomcminutes(20\d{6})(?:\.htm|/)", html))):
        # Minutes release is ~3 weeks after meeting end; Fed posts exact date when released.
        # Approximate only when link exists (already released or scheduled with page).
        approx = _ymd_et(ymd, 14, 0) + timedelta(days=21)
        while approx.weekday() != 2:
            approx += timedelta(days=1)
        sched = et_to_iso(approx.replace(hour=14, minute=0))
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "minutes", ymd),
                event_name="FOMC Meeting Minutes",
                category="fed",
                scheduled_at=sched,
                timezone="America/New_York",
                status=status_from_schedule(sched, now),
                source_name="Federal Reserve FOMC Calendars",
                source_url=f"{BASE}/monetarypolicy/fomcminutes{ymd}.htm",
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="partial",
                event_subtype="minutes",
                reference_period=f"meeting_end_{ymd}",
                scheduled_date=approx.date().isoformat(),
                time_status="approximate",
                notes=(
                    f"Minutes linked to meeting end {ymd}; publication day approximated "
                    "as ~3 weeks later (Wed 2pm ET). Treat as partial until Fed posts exact time."
                ),
            )
        )

    # --- Future / all meetings from year sections (table text, not CSS classes) ---
    # Page structure (2026+):
    #   #### 2026 FOMC Meetings
    #   **January**
    #   27-28
    #   **Statement:** ... (optional for past)
    #   **October**
    #   27-28
    year_blocks = re.split(
        r"(?i)(?:#{1,6}\s*|<(?:h[1-6]|strong|b)[^>]*>)\s*(\d{4})\s+FOMC\s+Meetings",
        html,
    )
    # Also try plain-text year headers from simplified HTML
    if len(year_blocks) < 3:
        year_blocks = re.split(r"(?i)(\d{4})\s+FOMC\s+Meetings", html)

    i = 1
    while i + 1 < len(year_blocks):
        try:
            year = int(year_blocks[i].strip())
        except ValueError:
            i += 2
            continue
        body = year_blocks[i + 1]
        # Stop at next year section roughly
        body = re.split(r"(?i)\d{4}\s+FOMC\s+Meetings", body)[0]

        # Match **Month** / <strong>Month</strong> followed by date range
        month_date_pairs = re.findall(
            r"(?i)(?:\*\*|<(?:strong|b|h[1-6])[^>]*>)\s*"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s*(?:\*\*|</(?:strong|b|h[1-6])>)\s*"
            r"(?:<[^>]+>\s*)*"
            r"(\d{1,2}\s*[-–]\s*\d{1,2}\*?|\d{1,2}\*?)",
            body,
        )
        # Fallback: Month name on its own line then date range
        if not month_date_pairs:
            month_date_pairs = re.findall(
                r"(?i)(?:^|\n)\s*(January|February|March|April|May|June|July|"
                r"August|September|October|November|December)\s*\n+\s*"
                r"(\d{1,2}\s*[-–]\s*\d{1,2}\*?|\d{1,2}\*?)",
                body,
            )

        for month_name, date_str in month_date_pairs:
            ymd = _parse_end_day(date_str, month_name, year)
            if not ymd:
                continue
            sched_date = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"

            if ymd not in seen_s:
                seen_s.add(ymd)
                # Future meetings: NO invented clock time
                events.append(
                    CalendarEvent(
                        event_id=make_event_id("fomc", "statement", ymd),
                        event_name="FOMC Statement / Rate Decision",
                        category="fed",
                        scheduled_at=None,
                        timezone="America/New_York",
                        status="scheduled",
                        source_name="Federal Reserve FOMC Calendars",
                        source_url=FOMC_URL,
                        retrieved_at=retrieved,
                        last_updated_at=retrieved,
                        data_quality="partial",
                        event_subtype="statement",
                        scheduled_date=sched_date,
                        time_status="unverified",
                        notes=f"Table {month_name} {date_str.strip()} {year}; end-day only, time not confirmed by Fed page",
                    )
                )
            if ymd not in seen_p:
                seen_p.add(ymd)
                events.append(
                    CalendarEvent(
                        event_id=make_event_id("fomc", "press_conference", ymd),
                        event_name="FOMC Press Conference",
                        category="fed",
                        scheduled_at=None,
                        timezone="America/New_York",
                        status="scheduled",
                        source_name="Federal Reserve FOMC Calendars",
                        source_url=FOMC_URL,
                        retrieved_at=retrieved,
                        last_updated_at=retrieved,
                        data_quality="partial",
                        event_subtype="press_conference",
                        scheduled_date=sched_date,
                        time_status="unverified",
                        notes=f"Table {month_name} {date_str.strip()} {year}; end-day only, time not confirmed",
                    )
                )
        i += 2

    return events


class FomcCalendarProvider:
    def fetch(self, window_start=None, window_end=None):
        now = datetime.now(timezone.utc)
        window_start = window_start or (now - timedelta(days=21))
        window_end = window_end or (now + timedelta(days=400))
        try:
            resp = requests.get(
                FOMC_URL, timeout=30, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            all_ev = parse_fomc_html(resp.text, now=now)
        except Exception as e:
            return [], f"FOMC calendar: {type(e).__name__}: {e}"

        out = []
        for ev in all_ev:
            # scheduled_date-only future events
            if ev.scheduled_at is None and ev.scheduled_date:
                try:
                    d = datetime.strptime(ev.scheduled_date, "%Y-%m-%d").replace(
                        tzinfo=ET
                    )
                    d_utc = d.astimezone(timezone.utc)
                    # Keep if within window (date-level)
                    if window_start.date() <= d_utc.date() <= window_end.date():
                        out.append(ev)
                except Exception:
                    out.append(ev)
                continue
            if not ev.scheduled_at:
                continue
            try:
                dt = datetime.fromisoformat(ev.scheduled_at)
            except Exception:
                continue
            if window_start <= dt.astimezone(timezone.utc) <= window_end:
                out.append(ev)
        return out, None
