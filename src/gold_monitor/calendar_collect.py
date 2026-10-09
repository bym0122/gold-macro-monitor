"""Merge official calendar providers and persist JSON (history-preserving)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from gold_monitor.providers.calendar_bls import BlsCalendarProvider
from gold_monitor.providers.calendar_bea import BeaCalendarProvider
from gold_monitor.providers.calendar_fomc import FomcCalendarProvider
from gold_monitor.providers.calendar_common import CalendarEvent


def merge_events(existing: list[dict], new_events: list[CalendarEvent]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for e in existing:
        eid = e.get("event_id")
        if eid:
            by_id[eid] = e
    for ev in new_events:
        d = ev.to_dict()
        eid = d["event_id"]
        if eid in by_id:
            # Preserve any previously filled actual/previous if we still don't have them
            old = by_id[eid]
            for k in ("actual", "previous", "consensus"):
                if d.get(k) is None and old.get(k) is not None:
                    d[k] = old[k]
            d["last_updated_at"] = d.get("retrieved_at") or old.get("last_updated_at")
        by_id[eid] = d
    merged = list(by_id.values())
    merged.sort(key=lambda x: x.get("scheduled_at") or "")
    return merged


def collect_calendar(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(".")
    now = datetime.now(timezone.utc)
    report_date = now.date().isoformat()

    errors: list[str] = []
    all_new: list[CalendarEvent] = []

    for name, provider in (
        ("bls", BlsCalendarProvider()),
        ("bea", BeaCalendarProvider()),
        ("fomc", FomcCalendarProvider()),
    ):
        evs, err = provider.fetch()
        if err:
            errors.append(err)
        all_new.extend(evs)

    cal_dir = root / "data" / "calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    path = cal_dir / f"{report_date}.json"

    existing: list[dict] = []
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            existing = list(prev.get("events") or [])
        except Exception:
            existing = []

    # Also merge from recent history files (7 days) so re-runs don't drop prior days' events
    for fp in sorted(cal_dir.glob("*.json"))[-14:]:
        if fp.name == path.name:
            continue
        try:
            prev = json.loads(fp.read_text(encoding="utf-8"))
            for e in prev.get("events") or []:
                if e.get("event_id") and e["event_id"] not in {x.get("event_id") for x in existing}:
                    existing.append(e)
        except Exception:
            continue

    merged = merge_events(existing, all_new)

    # Split upcoming 7d vs recent past 14d for consumers
    upcoming = []
    recent = []
    horizon = now + timedelta(days=7)
    past_floor = now - timedelta(days=14)
    for e in merged:
        sa = e.get("scheduled_at")
        if not sa:
            continue
        try:
            dt = datetime.fromisoformat(sa.replace("Z", "+00:00"))
        except Exception:
            continue
        if now <= dt <= horizon:
            upcoming.append(e)
        elif past_floor <= dt < now:
            recent.append(e)

    core_ok = any("BLS" in (e.get("source_name") or "") for e in merged) or not any(
        "BLS" in err for err in errors
    )
    payload = {
        "schema_version": "calendar_v1",
        "report_date": report_date,
        "generated_at_utc": now.isoformat(),
        "events": merged,
        "upcoming_7d": upcoming,
        "recent_14d": recent,
        "collection_stats": {
            "new_fetched": len(all_new),
            "merged_total": len(merged),
            "upcoming_7d_count": len(upcoming),
            "recent_14d_count": len(recent),
            "errors": errors,
            "core_sources_warning": (
                None
                if not errors
                else ("One or more calendar sources failed; see errors")
            ),
            "note": (
                "Official schedules only. actual/previous/consensus are null unless a future "
                "release-value parser is added. past_unverified means the release time passed "
                "but this pipeline did not capture published figures."
            ),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "payload": payload}
