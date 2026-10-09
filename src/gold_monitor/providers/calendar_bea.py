"""BEA public news schedule (PCE / Personal Income and Outlays)."""

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

SCHEDULE_URL = "https://www.bea.gov/news/schedule"
USER_AGENT = "gold-macro-monitor/0.8 (research; calendar; +https://github.com/bym0122/gold-macro-monitor)"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_bea_datetime(date_text: str, time_text: str, year: int) -> Optional[datetime]:
    """e.g. date_text='October 29', time_text='8:30 AM', year=2026 → ET"""
    date_text = (date_text or "").strip()
    time_text = (time_text or "").strip()
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})", date_text)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    day = int(m.group(2))
    tm = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_text, re.I)
    hour, minute = 8, 30
    if tm:
        hour = int(tm.group(1))
        minute = int(tm.group(2))
        ap = tm.group(3).upper()
        if ap == "PM" and hour != 12:
            hour += 12
        if ap == "AM" and hour == 12:
            hour = 0
    try:
        return datetime(year, mon, day, hour, minute, tzinfo=ET)
    except ValueError:
        return None


def parse_bea_html(html: str, now: Optional[datetime] = None) -> list[CalendarEvent]:
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []

    # Year headers and rows are interleaved; track current year
    year = now.astimezone(ET).year
    # Prefer explicit "Year 2026" markers
    chunks = re.split(r"Year\s+(202\d)", html)
    # If split worked: [before, year1, body1, year2, body2, ...]
    bodies: list[tuple[int, str]] = []
    if len(chunks) >= 3:
        for i in range(1, len(chunks), 2):
            bodies.append((int(chunks[i]), chunks[i + 1] if i + 1 < len(chunks) else ""))
    else:
        bodies = [(year, html)]

    for y, body in bodies:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S | re.I)
        for row in rows:
            texts = [re.sub(r"\s+", " ", x).strip() for x in re.findall(r">([^<]+)<", row) if x.strip()]
            if not texts:
                continue
            joined = " ".join(texts)
            if "Personal Income and Outlays" not in joined:
                continue
            # Expect something like: October 29 | 8:30 AM | News | Personal Income and Outlays, September 2026
            date_text = None
            time_text = "8:30 AM"
            title = None
            for i, t in enumerate(texts):
                if re.match(r"[A-Za-z]+\s+\d{1,2}$", t):
                    date_text = t
                    if i + 1 < len(texts) and re.search(r"AM|PM", texts[i + 1], re.I):
                        time_text = texts[i + 1]
                if "Personal Income and Outlays" in t:
                    title = t
            if not date_text or not title:
                continue
            dt = _parse_bea_datetime(date_text, time_text, y)
            if not dt:
                continue
            scheduled = et_to_iso(dt)
            ref = None
            rm = re.search(r"Personal Income and Outlays,?\s*(.+)$", title)
            if rm:
                ref = rm.group(1).strip()
            eid = make_event_id("bea", "personal_income_outlays", scheduled)
            events.append(
                CalendarEvent(
                    event_id=eid,
                    event_name="Personal Income and Outlays (includes PCE)",
                    category="consumption",
                    scheduled_at=scheduled,
                    timezone="America/New_York",
                    status=status_from_schedule(scheduled, now),
                    previous=None,
                    actual=None,
                    consensus=None,
                    unit=None,
                    source_name="BEA News Schedule",
                    source_url=SCHEDULE_URL,
                    retrieved_at=retrieved,
                    last_updated_at=retrieved,
                    data_quality="official",
                    notes="Schedule only; PCE detail is inside this release; no actuals from calendar page",
                    reference_period=ref,
                    event_subtype="data_release",
                )
            )
    return events


class BeaCalendarProvider:
    def fetch(
        self,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> tuple[list[CalendarEvent], Optional[str]]:
        now = datetime.now(timezone.utc)
        window_start = window_start or (now - timedelta(days=14))
        window_end = window_end or (now + timedelta(days=14))
        try:
            resp = requests.get(
                SCHEDULE_URL, timeout=30, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            all_ev = parse_bea_html(resp.text, now=now)
        except Exception as e:
            return [], f"BEA schedule: {type(e).__name__}: {e}"

        out = []
        for ev in all_ev:
            if not ev.scheduled_at:
                continue
            dt = datetime.fromisoformat(ev.scheduled_at)
            if window_start <= dt.astimezone(timezone.utc) <= window_end:
                out.append(ev)
        return out, None
