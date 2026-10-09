"""Shared calendar event model and helpers (no AI, no invented values)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass
class CalendarEvent:
    event_id: str
    event_name: str
    category: str  # employment | inflation | fed | consumption | other | unknown
    scheduled_at: Optional[str]  # ISO8601 with offset
    timezone: str
    status: str  # scheduled | past_unverified | released | unknown
    previous: Optional[float | str] = None
    actual: Optional[float | str] = None
    consensus: Optional[float | str] = None
    unit: Optional[str] = None
    source_name: str = ""
    source_url: str = ""
    retrieved_at: str = ""
    last_updated_at: Optional[str] = None
    data_quality: str = "official"  # official | secondary | partial | unverified
    notes: Optional[str] = None
    reference_period: Optional[str] = None
    event_subtype: Optional[str] = None  # e.g. statement | minutes | press_conference

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_event_id(*parts: str) -> str:
    key = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def et_to_iso(dt_local: datetime) -> str:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=ET)
    return dt_local.isoformat()


def classify_bls_summary(summary: str) -> tuple[str, str]:
    """Map BLS ICS SUMMARY to (category, normalized_name) via fixed rules only."""
    s = summary or ""
    sl = s.lower()
    if "employment situation" in sl:
        return "employment", "Employment Situation (NFP / unemployment / AHE)"
    if "job openings and labor turnover" in sl or "jolts" in sl:
        return "employment", "Job Openings and Labor Turnover (JOLTS)"
    if "consumer price index" in sl:
        return "inflation", "Consumer Price Index (CPI)"
    if "producer price index" in sl:
        return "inflation", "Producer Price Index (PPI)"
    if "real earnings" in sl:
        return "employment", "Real Earnings"
    if "initial" in sl and "claim" in sl:
        return "employment", s
    return "other", s


def status_from_schedule(scheduled_at_iso: Optional[str], now: Optional[datetime] = None) -> str:
    """Future → scheduled; past → past_unverified (no actual values claimed)."""
    if not scheduled_at_iso:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(scheduled_at_iso.replace("Z", "+00:00"))
    except Exception:
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt > now + timedelta(minutes=5):
        return "scheduled"
    return "past_unverified"


def parse_bls_ics_dtstart(raw: str) -> Optional[datetime]:
    """Parse DTSTART;TZID=US-Eastern:20250110T083000 or DTSTART:20250110T133000Z"""
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z") and "T" in raw:
        try:
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    # strip TZID prefix if passed as full line value only
    m = re.match(r"(\d{8}T\d{6})", raw)
    if not m:
        return None
    try:
        local = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=ET)
        return local
    except ValueError:
        return None
