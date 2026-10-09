"""Common data contracts for all providers."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class DataStatus(str, Enum):
    OK = "ok"
    STALE = "stale"
    MISSING = "missing"
    INVALID = "invalid"
    ESTIMATED = "estimated"


@dataclass
class MetricPoint:
    metric: str
    value: Optional[float]
    unit: str
    source: str
    source_url: str
    observation_date: Optional[str]  # YYYY-MM-DD
    fetched_at_utc: str
    status: DataStatus
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def missing(
        cls,
        metric: str,
        unit: str,
        source: str,
        source_url: str,
        notes: str = "",
    ) -> "MetricPoint":
        return cls(
            metric=metric,
            value=None,
            unit=unit,
            source=source,
            source_url=source_url,
            observation_date=None,
            fetched_at_utc=datetime.now(timezone.utc).isoformat(),
            status=DataStatus.MISSING,
            notes=notes or "No data returned",
        )
