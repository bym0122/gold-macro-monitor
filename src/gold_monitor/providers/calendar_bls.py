"""BLS official release calendar via public ICS (no paid API)."""

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
USER_AGENT = "gold-macro-monitor/0.8 (research; calendar; +https://github.com/bym0122/gold-macro-monitor)"

# Only keep high-priority / listed series from ICS (fixed allowlist)
ALLOW_SUBSTR = (
    "employment situation",
    "consumer price index",
    "producer price index",
    "job openings and labor turnover",
    "real earnings",
)


def _unfold_ics(text: str) -> str:
    # RFC 5545 line folding: CRLF + space/tab
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


class BlsCalendarProvider:
    def fetch(
        self,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> tuple[list[CalendarEvent], Optional[str]]:
        """Return (events, error)."""
        now = datetime.now(timezone.utc)
        window_start = window_start or (now - timedelta(days=14))
        window_end = window_end or (now + timedelta(days=14))
        try:
            resp = requests.get(
                ICS_URL, timeout=30, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            all_ev = parse_ics(resp.text, now=now)
        except Exception as e:
            return [], f"BLS ICS: {type(e).__name__}: {e}"

        out = []
        for ev in all_ev:
            if not ev.scheduled_at:
                continue
            try:
                dt = datetime.fromisoformat(ev.scheduled_at)
            except Exception:
                continue
            if window_start <= dt.astimezone(timezone.utc) <= window_end:
                out.append(ev)
        return out, None
