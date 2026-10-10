"""Market structure calendar provider (quadruple witching, month/quarter/year end).

Stub implementation: returns empty events until a real schedule source is wired.
Keeps calendar_collect importable and tests green.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from gold_monitor.providers.calendar_common import CalendarEvent


class MarketStructureCalendarProvider:
    """Placeholder provider for market-structure calendar events."""

    source_name = "market_structure"

    def fetch(self) -> Tuple[List[CalendarEvent], Optional[str]]:
        # No external schedule wired yet; return empty (no error).
        return [], None
