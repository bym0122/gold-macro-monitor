"""Fed FOMC calendar: meetings, statements, press conferences, minutes."""

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
USER_AGENT = "gold-macro-monitor/0.8 (research; calendar; +https://github.com/bym0122/gold-macro-monitor)"
BASE = "https://www.federalreserve.gov"


def _yyyymmdd_to_et_afternoon(yyyymmdd: str, hour: int = 14, minute: int = 0) -> datetime:
    """FOMC statements typically ~2:00 p.m. ET on the final meeting day."""
    y = int(yyyymmdd[0:4])
    m = int(yyyymmdd[4:6])
    d = int(yyyymmdd[6:8])
    return datetime(y, m, d, hour, minute, tzinfo=ET)


def parse_fomc_html(html: str, now: Optional[datetime] = None) -> list[CalendarEvent]:
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []

    # Statement release pages encode the decision day
    statement_dates = sorted(set(re.findall(r"/newsevents/pressreleases/monetary(20\d{6})a\.htm", html)))
    press_dates = sorted(set(re.findall(r"/monetarypolicy/fomcpres+conf(20\d{6})\.htm", html, re.I)))
    minutes_dates = sorted(set(re.findall(r"/monetarypolicy/fomcminutes(20\d{6})(?:\.htm|/)", html)))

    for ymd in statement_dates:
        dt = _yyyymmdd_to_et_afternoon(ymd, 14, 0)
        scheduled = et_to_iso(dt)
        url = f"{BASE}/newsevents/pressreleases/monetary{ymd}a.htm"
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "statement", ymd),
                event_name="FOMC Statement / Rate Decision",
                category="fed",
                scheduled_at=scheduled,
                timezone="America/New_York",
                status=status_from_schedule(scheduled, now),
                previous=None,
                actual=None,
                consensus=None,
                unit=None,
                source_name="Federal Reserve FOMC Calendars",
                source_url=url,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                notes="Time assumed 2:00 p.m. ET (standard post-meeting release window); not a tick-level guarantee",
                event_subtype="statement",
            )
        )

    for ymd in press_dates:
        dt = _yyyymmdd_to_et_afternoon(ymd, 14, 30)
        scheduled = et_to_iso(dt)
        url = f"{BASE}/monetarypolicy/fomcpresconf{ymd}.htm"
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "press_conference", ymd),
                event_name="FOMC Press Conference",
                category="fed",
                scheduled_at=scheduled,
                timezone="America/New_York",
                status=status_from_schedule(scheduled, now),
                source_name="Federal Reserve FOMC Calendars",
                source_url=url,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                notes="Time assumed 2:30 p.m. ET after statement; confirm on Fed site for exceptions",
                event_subtype="press_conference",
            )
        )

    for ymd in minutes_dates:
        # Minutes published three weeks later typically; the date in URL is the *meeting* end date,
        # not the publication date. We record meeting-associated minutes link without inventing publish day
        # unless we only have meeting day — mark scheduled_at as null for publish time unknown.
        url = f"{BASE}/monetarypolicy/fomcminutes{ymd}.htm"
        # Publication is usually Wednesday three weeks after meeting — approximate only with note
        meet = _yyyymmdd_to_et_afternoon(ymd, 14, 0)
        approx_pub = meet + timedelta(days=21)
        # Snap to Wednesday 14:00 ET roughly
        while approx_pub.weekday() != 2:  # Wednesday
            approx_pub += timedelta(days=1)
        approx_pub = approx_pub.replace(hour=14, minute=0)
        scheduled = et_to_iso(approx_pub)
        events.append(
            CalendarEvent(
                event_id=make_event_id("fomc", "minutes", ymd),
                event_name="FOMC Meeting Minutes",
                category="fed",
                scheduled_at=scheduled,
                timezone="America/New_York",
                status=status_from_schedule(scheduled, now),
                source_name="Federal Reserve FOMC Calendars",
                source_url=url,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="partial",
                notes=(
                    f"Minutes linked to meeting end {ymd}; publication day approximated as ~3 weeks later "
                    "(Wed 2pm ET). Treat as partial until Fed posts exact time."
                ),
                event_subtype="minutes",
                reference_period=f"meeting_end_{ymd}",
            )
        )

    return events


class FomcCalendarProvider:
    def fetch(
        self,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> tuple[list[CalendarEvent], Optional[str]]:
        now = datetime.now(timezone.utc)
        # Wider window for Fed: include more future meetings
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
