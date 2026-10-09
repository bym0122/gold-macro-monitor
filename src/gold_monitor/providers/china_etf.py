"""China Gold ETF 159934 provider interface.

IMPORTANT: Validate source for NAV vs market price, timezone and ToS
before enabling automatic collection.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import MetricPoint, DataStatus


class ChinaGoldETFProvider:
    """Placeholder for 159934."""

    def get_159934(self) -> list[MetricPoint]:
        base_notes = (
            "No validated free 159934 source configured yet. "
            "Implement after testing candidates in config/sources.yaml. "
            "Do not invent values."
        )
        now = datetime.now(timezone.utc).isoformat()
        return [
            MetricPoint(
                metric="etf_159934_close",
                value=None,
                unit="CNY",
                source="placeholder",
                source_url="",
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.MISSING,
                notes=base_notes,
            ),
            MetricPoint(
                metric="etf_159934_change_pct",
                value=None,
                unit="percent",
                source="placeholder",
                source_url="",
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.MISSING,
                notes=base_notes,
            ),
        ]
