"""Status observability: partial sources must not be masked as full success."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

from gold_monitor.providers.calendar_common import CalendarEvent
from gold_monitor.providers.calendar_market_structure import (
    MarketStructureCalendarProvider,
    build_rule_events,
)


def _ev(name: str = "rule") -> CalendarEvent:
    now = datetime.now(timezone.utc).isoformat()
    return CalendarEvent(
        event_id=f"test-{name}",
        event_name=name,
        category="market_structure",
        scheduled_at=None,
        scheduled_date="2026-10-15",
        timezone="America/New_York",
        status="scheduled",
        source_name="Calendar rule (calculated)",
        source_url="",
        retrieved_at=now,
        last_updated_at=now,
        data_quality="calculated",
        notes="test",
        event_type="month_end_rebalance",
        event_subtype="calculated_rule",
        time_status="date_only",
    )


def test_rules_produce_events():
    now = datetime.now(timezone.utc)
    evs = build_rule_events(date(2026, 10, 1), date(2026, 12, 31), now)
    assert len(evs) >= 3
    assert all(e.data_quality == "calculated" for e in evs)


def test_cme_failure_returns_partial_err():
    provider = MarketStructureCalendarProvider()
    with patch(
        "gold_monitor.providers.calendar_market_structure.fetch_treasury_upcoming",
        return_value=([_ev("treasury")], None),
    ), patch(
        "gold_monitor.providers.calendar_market_structure.fetch_cme_gold_calendar",
        return_value=([], "CME gold calendar HTTP 403"),
    ):
        evs, err = provider.fetch()
    assert err is not None
    assert "CME" in err
    assert len(evs) >= 1
    assert any(e.event_type == "source_status" for e in evs)


def test_treasury_failure_returns_partial_err():
    provider = MarketStructureCalendarProvider()
    with patch(
        "gold_monitor.providers.calendar_market_structure.fetch_treasury_upcoming",
        return_value=([], "Treasury upcoming_auctions HTTP 500"),
    ), patch(
        "gold_monitor.providers.calendar_market_structure.fetch_cme_gold_calendar",
        return_value=([_ev("cme")], None),
    ):
        evs, err = provider.fetch()
    assert err is not None
    assert "Treasury" in err
    assert len(evs) >= 1


def test_partial_classification_logic():
    """err+events -> partial; pure err -> failed; ok -> ok."""
    providers = (
        ("bea", lambda: ([_ev("ok")], None)),
        ("market_structure", lambda: ([_ev("partial")], "CME gold calendar: parse_error")),
        ("bls", lambda: ([], "BLS ICS HTTP 403")),
    )
    errors, ok, failed, partial, detail = [], [], [], [], {}
    for name, fetch in providers:
        evs, err = fetch()
        if err and evs:
            errors.append(err)
            partial.append(name)
            detail[name] = f"partial | {err}"
        elif err and not evs:
            errors.append(err)
            failed.append(name)
            detail[name] = f"failed | {err}"
        else:
            ok.append(name)
            detail[name] = "ok"
    assert "bea" in ok
    assert "market_structure" in partial
    assert "bls" in failed
    assert "market_structure" not in ok
    assert "market_structure" not in failed
