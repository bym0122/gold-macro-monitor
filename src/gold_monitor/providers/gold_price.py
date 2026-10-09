"""Gold price provider interface.

IMPORTANT: No candidate is marked stable until validated for ToS,
accessibility, field mapping, timezone and update cadence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .base import MetricPoint, DataStatus


class GoldPriceProvider:
    """Placeholder. Replace primary after real-world validation."""

    def __init__(self, primary: str = "placeholder"):
        self.primary = primary

    def get_spot_or_futures(self) -> MetricPoint:
        # TODO: implement after choosing and validating a free source
        return MetricPoint(
            metric="gold_xauusd",
            value=None,
            unit="USD/oz",
            source="placeholder",
            source_url="",
            observation_date=None,
            fetched_at_utc=datetime.now(timezone.utc).isoformat(),
            status=DataStatus.MISSING,
            notes=(
                "No validated free gold price source configured yet. "
                "Implement GoldPriceProvider after testing candidates "
                "(see config/sources.yaml). Do not invent values."
            ),
        )
