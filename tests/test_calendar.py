"""Tests for official macro/Fed calendar parsing (local fixtures)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from gold_monitor.providers.calendar_bls import parse_ics
from gold_monitor.providers.calendar_bea import parse_bea_html, _parse_bea_datetime
from gold_monitor.providers.calendar_fomc import parse_fomc_html
from gold_monitor.providers.calendar_common import status_from_schedule, make_event_id
from gold_monitor.calendar_collect import merge_events
from gold_monitor.providers.calendar_common import CalendarEvent
from gold_monitor.providers.news import FEEDS


ICS_SAMPLE = """
BEGIN:VCALENDAR
BEGIN:VEVENT
UID:test-1
DTSTART;TZID=US-Eastern:20261015T083000
SUMMARY:Employment Situation
END:VEVENT
BEGIN:VEVENT
UID:test-2
DTSTART;TZID=US-Eastern:20261020T083000
SUMMARY:Consumer Price Index
END:VEVENT
BEGIN:VEVENT
UID:test-3
DTSTART;TZID=US-Eastern:20261022T083000
SUMMARY:Some Other Random Release
END:VEVENT
END:VCALENDAR
"""

BEA_SAMPLE = """
<html><body>
Year 2026
<tr class="scheduled-release">
<td>October 29</td><td>8:30 AM</td><td>News</td>
<td>Personal Income and Outlays, September 2026</td>
</tr>
<tr class="scheduled-release">
<td>November 25</td><td>8:30 AM</td><td>News</td>
<td>Personal Income and Outlays, October 2026</td>
</tr>
</body></html>
"""

FOMC_SAMPLE = """
<a href="/newsevents/pressreleases/monetary20261028a.htm">HTML</a>
<a href="/monetarypolicy/fomcpresconf20261028.htm">Press Conference</a>
<a href="/monetarypolicy/fomcminutes20261028.htm">HTML</a>
"""


def test_news_feeds_include_nfp_ppi():
    topics = {f["search_topic"] for f in FEEDS}
    names = {f["name"] for f in FEEDS}
    assert "us_nfp_employment" in topics or "GN-NFP" in names
    assert any("ppi" in t or "CPI" in n for n, t in zip(names, topics))


def test_bls_ics_parse_and_filter():
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    evs = parse_ics(ICS_SAMPLE, now=now)
    names = {e.event_name for e in evs}
    assert any("Employment" in n for n in names)
    assert any("CPI" in n or "Consumer" in n for n in names)
    assert not any("Random" in n for n in names)
    for e in evs:
        assert e.actual is None
        assert e.consensus is None
        assert e.source_url


def test_future_not_marked_released():
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    assert status_from_schedule(future) == "scheduled"
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert status_from_schedule(past) == "past_unverified"


def test_bea_pce_schedule():
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    evs = parse_bea_html(BEA_SAMPLE, now=now)
    assert len(evs) >= 1
    assert all("Personal Income" in e.event_name for e in evs)
    assert all(e.actual is None for e in evs)
    dt = _parse_bea_datetime("October 29", "8:30 AM", 2026)
    assert dt is not None
    assert dt.hour == 8 and dt.minute == 30


def test_fomc_subtypes_separate():
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    evs = parse_fomc_html(FOMC_SAMPLE, now=now)
    subtypes = {e.event_subtype for e in evs}
    assert "statement" in subtypes
    assert "press_conference" in subtypes
    assert "minutes" in subtypes
    ids = [e.event_id for e in evs]
    assert len(ids) == len(set(ids))


def test_merge_dedupes_by_event_id():
    e1 = CalendarEvent(
        event_id="abc",
        event_name="X",
        category="employment",
        scheduled_at="2026-10-15T08:30:00-04:00",
        timezone="America/New_York",
        status="scheduled",
        source_name="BLS",
        source_url="https://example.com",
        retrieved_at="t1",
    )
    e2 = CalendarEvent(
        event_id="abc",
        event_name="X",
        category="employment",
        scheduled_at="2026-10-15T08:30:00-04:00",
        timezone="America/New_York",
        status="scheduled",
        source_name="BLS",
        source_url="https://example.com",
        retrieved_at="t2",
    )
    merged = merge_events([], [e1, e2])
    assert len(merged) == 1


def test_event_id_stable():
    assert make_event_id("bls", "a", "b") == make_event_id("bls", "a", "b")
