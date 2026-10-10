"""BLS official release calendar: ICS primary + official HTML monthly schedule fallback."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from .calendar_common import (
    CalendarEvent,
    classify_bls_summary,
    et_to_iso,
    make_event_id,
    parse_bls_ics_dtstart,
    status_from_schedule,
    ET,
)

ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
HTML_SCHEDULE_TMPL = "https://www.bls.gov/schedule/{year}/{month:02d}_sched_list.htm"
USER_AGENT = (
    "gold-macro-monitor/0.9 (research; calendar; "
    "+https://github.com/bym0122/gold-macro-monitor)"
)

ALLOW_SUBSTR = (
    "employment situation",
    "consumer price index",
    "producer price index",
    "job openings and labor turnover",
    "real earnings",
    "employment cost index",
    "import and export price",
    "productivity and costs",
    "usual weekly earnings",
)

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _unfold_ics(text: str) -> str:
    return re.sub(r"\r\n[ \t]", "", text.replace("\r\n", "\n").replace("\r", "\n"))


def parse_ics(text: str, now: Optional[datetime] = None) -> list[CalendarEvent]:
    now = now or datetime.now(timezone.utc)
    text = _unfold_ics(text)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []

    for block in text.split("BEGIN:VEVENT")[1:]:
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            if ":" not in line or line.startswith(" "):
                continue
            key, val = line.split(":", 1)
            key_main = key.split(";")[0].upper()
            fields[key_main] = val.strip()
            if key_main == "DTSTART" and "TZID=" in key.upper():
                fields["DTSTART_RAW"] = val.strip()

        summary = fields.get("SUMMARY") or ""
        if not any(s in summary.lower() for s in ALLOW_SUBSTR):
            continue

        dt_raw = fields.get("DTSTART_RAW") or fields.get("DTSTART") or ""
        dt = parse_bls_ics_dtstart(dt_raw)
        if not dt:
            continue

        scheduled = et_to_iso(dt.astimezone(ET))
        cat, name = classify_bls_summary(summary)
        eid = make_event_id("bls", name, scheduled)
        events.append(
            CalendarEvent(
                event_id=eid,
                event_name=name,
                category=cat,
                scheduled_at=scheduled,
                timezone="America/New_York",
                status=status_from_schedule(scheduled, now),
                previous=None,
                actual=None,
                consensus=None,
                unit=None,
                source_name="BLS Release Schedule (ICS)",
                source_url=ICS_URL,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                notes="Schedule only; actual/previous/consensus not provided by ICS",
                event_subtype="data_release",
            )
        )
    return events


def _parse_html_time(time_text: str) -> tuple[int, int]:
    tm = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", (time_text or "").strip(), re.I)
    if not tm:
        return 8, 30
    hour, minute = int(tm.group(1)), int(tm.group(2))
    ap = (tm.group(3) or "AM").upper()
    if ap == "PM" and hour != 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    return hour, minute


def parse_bls_html_schedule(
    html: str,
    year: int,
    month: int,
    source_url: str,
    now: Optional[datetime] = None,
) -> list[CalendarEvent]:
    """Parse official BLS monthly list-view HTML schedule."""
    now = now or datetime.now(timezone.utc)
    retrieved = now.isoformat()
    events: list[CalendarEvent] = []

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</tr>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)

    pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s*(20\d{2})\s+"
        r"(\d{1,2}:\d{2}\s*(?:AM|PM)?)\s+"
        r"(.+?)(?=(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},\s*20\d{2}|NOTE:|Last Modified|$)",
        re.I | re.S,
    )

    for m in pattern.finditer(text):
        mon_name, day_s, year_s, time_s, release = m.groups()
        mon = MONTH_NAMES.get(mon_name.lower())
        if not mon:
            continue
        y, day = int(year_s), int(day_s)
        release = re.sub(r"\s+", " ", release).strip()
        if not release or len(release) < 5:
            continue
        if any(
            h in release.lower()
            for h in (
                "new year", "martin luther", "presidents", "memorial",
                "independence", "labor day", "columbus", "veterans",
                "thanksgiving", "christmas", "holiday",
            )
        ):
            continue
        if not any(s in release.lower() for s in ALLOW_SUBSTR):
            continue

        hour, minute = _parse_html_time(time_s)
        try:
            dt = datetime(y, mon, day, hour, minute, tzinfo=ET)
        except ValueError:
            continue

        scheduled = et_to_iso(dt)
        cat, name = classify_bls_summary(release)
        eid = make_event_id("bls", name, scheduled)
        events.append(
            CalendarEvent(
                event_id=eid,
                event_name=name,
                category=cat,
                scheduled_at=scheduled,
                timezone="America/New_York",
                status=status_from_schedule(scheduled, now),
                previous=None,
                actual=None,
                consensus=None,
                unit=None,
                source_name="BLS Release Schedule (HTML)",
                source_url=source_url,
                retrieved_at=retrieved,
                last_updated_at=retrieved,
                data_quality="official",
                notes="Schedule only; actuals not filled from calendar HTML",
                event_subtype="data_release",
            )
        )
    return events


def _unavailable_marker(
    source: str,
    url: str,
    http_status: Optional[int],
    error: str,
    now: datetime,
) -> CalendarEvent:
    retrieved = now.isoformat()
    return CalendarEvent(
        event_id=make_event_id("bls", "unavailable", retrieved[:16]),
        event_name="BLS calendar unavailable",
        category="bls",
        scheduled_at=None,
        timezone="America/New_York",
        status="unavailable",
        previous=None,
        actual=None,
        consensus=None,
        unit=None,
        source_name=source,
        source_url=url,
        retrieved_at=retrieved,
        last_updated_at=retrieved,
        data_quality="unavailable",
        notes=f"HTTP {http_status}: {error}" if http_status else error,
        event_subtype="source_status",
        time_status="unavailable",
    )


class BlsCalendarProvider:
    def fetch(
        self,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> tuple[list[CalendarEvent], Optional[str]]:
        """Return (events, error). Tries ICS first, then official HTML monthly pages."""
        now = datetime.now(timezone.utc)
        window_start = window_start or (now - timedelta(days=14))
        window_end = window_end or (now + timedelta(days=45))
        headers = {"User-Agent": USER_AGENT, "Accept": "text/calendar, text/html, */*"}
        errors: list[str] = []
        all_ev: list[CalendarEvent] = []

        ics_ok = False
        try:
            resp = requests.get(ICS_URL, timeout=30, headers=headers)
            if resp.status_code == 403:
                errors.append(f"BLS ICS: HTTP 403 Forbidden ({ICS_URL})")
            else:
                resp.raise_for_status()
                all_ev.extend(parse_ics(resp.text, now=now))
                ics_ok = True
        except Exception as e:
            errors.append(f"BLS ICS: {type(e).__name__}: {e}")

        if not ics_ok:
            et_now = now.astimezone(ET)
            months_to_try = []
            y, m = et_now.year, et_now.month
            if m == 1:
                months_to_try.append((y - 1, 12))
            else:
                months_to_try.append((y, m - 1))
            months_to_try.append((y, m))
            if m == 12:
                months_to_try.append((y + 1, 1))
            else:
                months_to_try.append((y, m + 1))

            html_ok = False
            for year, month in months_to_try:
                url = HTML_SCHEDULE_TMPL.format(year=year, month=month)
                try:
                    resp = requests.get(url, timeout=30, headers=headers)
                    if resp.status_code in (403, 404):
                        errors.append(f"BLS HTML: HTTP {resp.status_code} ({url})")
                        continue
                    resp.raise_for_status()
                    evs = parse_bls_html_schedule(resp.text, year, month, url, now=now)
                    if evs:
                        all_ev.extend(evs)
                        html_ok = True
                except Exception as e:
                    errors.append(f"BLS HTML {year}-{month:02d}: {type(e).__name__}: {e}")

            if not html_ok and not all_ev:
                all_ev.append(
                    _unavailable_marker(
                        "BLS",
                        ICS_URL,
                        403 if any("403" in e for e in errors) else None,
                        "; ".join(errors) if errors else "all BLS sources failed",
                        now,
                    )
                )
                return all_ev, "; ".join(errors) if errors else "BLS calendar unavailable"

        out: list[CalendarEvent] = []
        for ev in all_ev:
            if ev.status == "unavailable":
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

        err = "; ".join(errors) if errors and not ics_ok else None
        return out, err
