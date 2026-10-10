"""Merge official calendar providers + market structure and persist JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from gold_monitor.providers.calendar_bls import BlsCalendarProvider
from gold_monitor.providers.calendar_bea import BeaCalendarProvider
from gold_monitor.providers.calendar_fomc import FomcCalendarProvider
from gold_monitor.providers.calendar_common import CalendarEvent
from gold_monitor.providers.calendar_market_structure import MarketStructureCalendarProvider


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
            old = by_id[eid]
            for k in ("actual", "previous", "consensus"):
                if d.get(k) is None and old.get(k) is not None:
                    d[k] = old[k]
            d["last_updated_at"] = d.get("retrieved_at") or old.get("last_updated_at")
        by_id[eid] = d
    merged = list(by_id.values())
    merged.sort(
        key=lambda x: x.get("scheduled_at")
        or ((x.get("scheduled_date") or "") + "T00:00:00")
    )
    return merged


def _event_dt(e: dict) -> datetime | None:
    sa = e.get("scheduled_at")
    if sa:
        try:
            return datetime.fromisoformat(sa.replace("Z", "+00:00"))
        except Exception:
            pass
    sd = e.get("scheduled_date")
    if sd:
        try:
            return datetime.strptime(sd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def collect_calendar(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(".")
    now = datetime.now(timezone.utc)
    report_date = now.date().isoformat()

    errors: list[str] = []
    sources_ok: list[str] = []
    sources_failed: list[str] = []
    sources_partial: list[str] = []
    source_detail: dict[str, str] = {}
    all_new: list[CalendarEvent] = []

    providers = (
        ("bls", BlsCalendarProvider()),
        ("bea", BeaCalendarProvider()),
        ("fomc", FomcCalendarProvider()),
        ("market_structure", MarketStructureCalendarProvider()),
    )
    for name, provider in providers:
        try:
            evs, err = provider.fetch()
            if err and evs:
                errors.append(err)
                sources_partial.append(name)
                source_detail[name] = f"partial | {err}"
                all_new.extend(evs)
            elif err and not evs:
                errors.append(err)
                sources_failed.append(name)
                source_detail[name] = f"failed | {err}"
            elif evs:
                sources_ok.append(name)
                source_detail[name] = "ok"
                all_new.extend(evs)
            else:
                sources_ok.append(name)
                source_detail[name] = "ok | empty"
        except Exception as e:
            msg = f"{name}: {type(e).__name__}: {e}"
            errors.append(msg)
            sources_failed.append(name)
            source_detail[name] = f"failed | {type(e).__name__}: {e}"

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

    for fp in sorted(cal_dir.glob("*.json"))[-14:]:
        if fp.name == path.name:
            continue
        try:
            prev = json.loads(fp.read_text(encoding="utf-8"))
            for e in prev.get("events") or []:
                if e.get("event_id") and e["event_id"] not in {
                    x.get("event_id") for x in existing
                }:
                    existing.append(e)
        except Exception:
            continue

    merged = merge_events(existing, all_new)

    upcoming = []
    recent = []
    horizon = now + timedelta(days=7)
    past_floor = now - timedelta(days=14)
    for e in merged:
        if e.get("status") == "unavailable":
            continue
        dt = _event_dt(e)
        if not dt:
            continue
        if now <= dt <= horizon:
            upcoming.append(e)
        elif past_floor <= dt < now:
            recent.append(e)

    # Partition by category for schema 0.9
    economic = [
        e
        for e in merged
        if e.get("category") in ("employment", "inflation", "consumption", "activity", "other", "bls")
        or e.get("source_name", "").startswith("BLS")
        or e.get("source_name", "").startswith("BEA")
    ]
    fed = [e for e in merged if e.get("category") == "fed"]
    gold_deriv = [
        e
        for e in merged
        if e.get("event_type")
        in (
            "gold_futures_expiry",
            "gold_first_notice",
            "gold_last_trading",
            "gold_option_expiry",
            "gold_delivery",
        )
        or e.get("category") == "gold_derivatives"
    ]
    treasury = [
        e
        for e in merged
        if e.get("category") == "treasury" or e.get("event_type") == "treasury_auction"
    ]
    market_struct = [
        e
        for e in merged
        if e.get("category") == "market_structure"
        or e.get("event_type")
        in (
            "quadruple_witching",
            "month_end_rebalance",
            "quarter_end",
            "year_end",
            "rollover_window",
        )
    ]
    cot_cal = [
        e
        for e in merged
        if e.get("category") == "cot" or e.get("event_type") in ("cot_asof", "cot_release")
    ]

    payload = {
        "schema_version": "0.9",
        "report_date": report_date,
        "generated_at": now.isoformat(),
        "generated_at_utc": now.isoformat(),
        "events": merged,
        "upcoming_7d": upcoming,
        "recent_14d": recent,
        "economic_calendar": economic,
        "fed_calendar": fed,
        "gold_derivatives_calendar": gold_deriv,
        "treasury_calendar": treasury,
        "market_structure_calendar": market_struct,
        "cot_calendar": cot_cal,
        "collection_stats": {
            "new_fetched": len(all_new),
            "merged_total": len(merged),
            "upcoming_7d_count": len(upcoming),
            "recent_14d_count": len(recent),
            "errors": errors,
            "source_detail": source_detail,
            "core_sources_warning": (
                None
                if not errors
                else "One or more calendar sources failed or partial; see errors / source_detail"
            ),
            "note": (
                "Official schedules only. actual/previous/consensus are null unless a future "
                "release-value parser is added. Future FOMC meetings use scheduled_date with "
                "time_status=unverified (no invented clock time). "
                "market_structure may be partial when CME/Treasury soft-fail while rules succeed."
            ),
        },
        "data_quality": {
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "sources_partial": sources_partial,
            "source_detail": source_detail,
            "warnings": errors,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "payload": payload}
