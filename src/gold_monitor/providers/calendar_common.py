"""Shared calendar models and helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass
class CalendarEvent:
    event_id: str
    event_name: str
    category: str
    scheduled_at: Optional[str]
    timezone: str = "America/New_York"
    status: str = "scheduled"
    previous: Optional[Any] = None
    actual: Optional[Any] = None
    consensus: Optional[Any] = None
    unit: Optional[str] = None
    source_name: str = ""
    source_url: str = ""
    retrieved_at: str = ""
    last_updated_at: Optional[str] = None
    data_quality: str = "official"
    notes: Optional[str] = None
    reference_period: Optional[str] = None
    event_subtype: Optional[str] = None
    scheduled_date: Optional[str] = None
    time_status: Optional[str] = None
    event_type: Optional[str] = None
    contract: Optional[str] = None
    contract_month: Optional[str] = None
    risk_level: Optional[str] = None
    direction: Optional[str] = "neutral"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None or k in (
            "scheduled_at", "previous", "actual", "consensus", "unit", "notes"
        )}


def make_event_id(*parts: str) -> str:
    key = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def et_to_iso(dt_local: datetime) -> str:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=ET)
    return dt_local.isoformat()


def classify_bls_summary(summary: str) -> tuple[str, str]:
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
    if "import" in sl and "price" in sl:
        return "inflation", "U.S. Import and Export Price Indexes"
    if "retail" in sl:
        return "activity", s
    if "initial" in sl and "claim" in sl:
        return "employment", s
    if "productivity" in sl:
        return "activity", s
    return "other", s


def status_from_schedule(scheduled_at_iso: Optional[str], now: Optional[datetime] = None) -> str:
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
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z") and "T" in raw:
        try:
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    m = re.match(r"(\d{8}T\d{6})", raw)
    if not m:
        return None
    try:
        local = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=ET)
        return local
    except ValueError:
        return None


def event_sort_key(e: dict[str, Any]) -> str:
    return e.get("scheduled_at") or (e.get("scheduled_date") or "") + "T00:00:00"
