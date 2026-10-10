"""Unit tests for market-structure calendar rules (no network)."""

from datetime import date, datetime, timezone

from gold_monitor.providers.calendar_market_structure import (
    _month_end,
    _third_friday,
    build_rule_events,
)


def test_third_friday_known():
    # 2026-03-20 is 3rd Friday of March 2026
    assert _third_friday(2026, 3) == date(2026, 3, 20)
    assert _third_friday(2026, 6) == date(2026, 6, 19)
    assert _third_friday(2026, 9) == date(2026, 9, 18)
    assert _third_friday(2026, 12) == date(2026, 12, 18)


def test_month_end_leap():
    assert _month_end(2024, 2) == date(2024, 2, 29)
    assert _month_end(2025, 2) == date(2025, 2, 28)
    assert _month_end(2026, 10) == date(2026, 10, 31)


def test_build_rule_events_window():
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    evs = build_rule_events(date(2026, 10, 1), date(2026, 12, 31), now)
    types = {e.event_type for e in evs}
    assert "month_end_rebalance" in types or "quarter_end" in types or "year_end" in types
    assert "quadruple_witching" in types
    # Dec year-end + Dec witching
    dates = {e.scheduled_date for e in evs}
    assert "2026-12-31" in dates
    assert "2026-12-18" in dates
    for e in evs:
        assert e.data_quality == "calculated"
        assert e.category == "market_structure"
        assert e.scheduled_at is None
