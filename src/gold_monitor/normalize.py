"""Normalize raw provider outputs into consistent MetricPoint lists."""

from __future__ import annotations

from typing import Iterable

from .providers.base import MetricPoint


def normalize_metrics(points: Iterable[MetricPoint]) -> list[dict]:
    return [p.to_dict() for p in points]
