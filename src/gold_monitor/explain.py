"""Data-quality helpers only.

Does NOT produce news event clusters, gold direction, or most_likely causality.
Those analyses are out of scope for Actions (ChatGPT reads news JSON later).
"""

from __future__ import annotations

from typing import Any, Optional

from .providers.base import MetricPoint, DataStatus


def _val(metrics: dict[str, MetricPoint], key: str) -> Optional[float]:
    p = metrics.get(key)
    if p and p.status in (DataStatus.OK, DataStatus.STALE) and p.value is not None:
        return p.value
    return None


def data_quality_notes(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
) -> list[str]:
    """Neutral checks: missing series, insufficient history — no causal claims."""
    notes: list[str] = []
    for key, label in [
        ("gold_xauusd", "XAU/USD"),
        ("dxy", "DXY"),
        ("us_10y_real_yield", "10Y real yield"),
        ("us_10y_nominal_yield", "10Y nominal yield"),
        ("etf_159934_close", "159934"),
    ]:
        p = metrics.get(key)
        if not p or p.status == DataStatus.MISSING:
            notes.append(f"{label}: missing")
        elif p.status == DataStatus.INVALID:
            notes.append(f"{label}: invalid ({p.notes or 'no detail'})")
        elif p.status == DataStatus.STALE:
            notes.append(f"{label}: stale observation_date={p.observation_date}")

    for name in ("gold_xauusd", "dxy", "us_10y_real_yield"):
        hist = (indicator_snap.get(name) or {}).get("history_points") or 0
        if hist < 2:
            notes.append(f"{name}: history_points={hist} (1d change not reliable yet)")
    return notes


# Back-compat shims so old imports do not crash; return empty / deprecated markers.
def candidate_explanations(*_args, **_kwargs) -> list[dict[str, Any]]:
    return [
        {
            "title": "deprecated",
            "support": "v0.5+ Actions no longer emit causal news explanations",
            "counter": "—",
            "confidence": "n/a",
            "todo": "Use ChatGPT on data/news/*.json",
            "legacy": True,
        }
    ]


def build_layered_analysis(*_args, **_kwargs) -> dict[str, Any]:
    return {
        "schema_version": "analysis_deprecated_v0",
        "note": "Causal analysis removed from Actions pipeline",
        "most_likely": None,
        "confidence": None,
        "layers": [],
        "event_analysis": [],
    }
