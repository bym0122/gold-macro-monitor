"""Validation helpers – never silently replace missing/stale with 0."""

from __future__ import annotations

from .providers.base import MetricPoint, DataStatus


def summarize_statuses(points: list[MetricPoint]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in points:
        key = p.status.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def has_critical_missing(points: list[MetricPoint], critical_metrics: set[str]) -> bool:
    for p in points:
        if p.metric in critical_metrics and p.status in (
            DataStatus.MISSING,
            DataStatus.INVALID,
        ):
            return True
    return False
