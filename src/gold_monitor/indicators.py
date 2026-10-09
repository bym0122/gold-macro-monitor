"""Reproducible indicators from metric history (JSON files).

Price series: relative % change.
Yield / rate series (stored as percent levels): absolute change in percentage
points and basis points (bps). Never invent changes when history is thin or
observation_date did not advance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Metrics treated as yield/rate levels (unit: percent)
YIELD_METRICS = frozenset(
    {
        "us_10y_real_yield",
        "us_10y_nominal_yield",
        "us_10y_breakeven_inflation",
    }
)

PRICE_METRICS = frozenset(
    {
        "gold_xauusd",
        "dxy",
        "usd_cny",
        "etf_159934_close",
    }
)


def load_recent_observations(
    metric: str,
    max_files: int = 90,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load unique observations keyed by observation_date (not report_date).

    Each entry: {observation_date, value, report_date, fetched_at_utc}.
    Newer report files first; first seen observation_date wins (most recent fetch).
    """
    root = root or Path("data/daily")
    if not root.exists():
        return []
    seen_obs: set[str] = set()
    out: list[dict[str, Any]] = []
    files = sorted(root.rglob("*.json"), reverse=True)
    for fp in files[:max_files]:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        report_date = payload.get("report_date") or fp.stem
        for m in payload.get("metrics") or []:
            if m.get("metric") != metric:
                continue
            if m.get("value") is None:
                continue
            obs = m.get("observation_date")
            if not obs:
                # No observation_date → cannot safely chain history
                continue
            if obs in seen_obs:
                # Same FRED observation repeated across report days — skip duplicate
                continue
            seen_obs.add(obs)
            try:
                val = float(m["value"])
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "observation_date": obs,
                    "value": val,
                    "report_date": report_date,
                    "fetched_at_utc": m.get("fetched_at_utc"),
                }
            )
            break
    # Sort by observation_date descending (newest first)
    out.sort(key=lambda x: x["observation_date"], reverse=True)
    return out


def load_recent_metric_values(metric: str, max_days: int = 90) -> list[tuple[str, float]]:
    """Back-compat: (observation_date, value) newest first."""
    return [(o["observation_date"], o["value"]) for o in load_recent_observations(metric, max_days)]


def pct_change(values: list[float], lag: int) -> Optional[float]:
    if len(values) <= lag:
        return None
    a, b = values[0], values[lag]
    if b == 0:
        return None
    return (a - b) / abs(b) * 100.0


def abs_change(values: list[float], lag: int) -> Optional[float]:
    """Absolute difference of levels (percentage points for yields)."""
    if len(values) <= lag:
        return None
    return values[0] - values[lag]


def compute_metric_change(metric: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [o["value"] for o in observations]
    base: dict[str, Any] = {
        "history_points": len(vals),
        "latest_observation_date": observations[0]["observation_date"] if observations else None,
        "prior_observation_date": observations[1]["observation_date"] if len(observations) > 1 else None,
        "chg_1d_pct": None,
        "chg_5d_pct": None,
        "chg_1_obs_pp": None,  # percentage points (levels)
        "chg_1_obs_bps": None,
        "chg_5_obs_pp": None,
        "chg_5_obs_bps": None,
        "kind": "yield" if metric in YIELD_METRICS else ("price" if metric in PRICE_METRICS else "other"),
    }
    if metric in YIELD_METRICS:
        d1 = abs_change(vals, 1)
        d5 = abs_change(vals, 5)
        base["chg_1_obs_pp"] = d1
        base["chg_1_obs_bps"] = (d1 * 100.0) if d1 is not None else None
        base["chg_5_obs_pp"] = d5
        base["chg_5_obs_bps"] = (d5 * 100.0) if d5 is not None else None
        # Do not populate misleading relative % for yields
        base["chg_1d_pct"] = None
        base["chg_5d_pct"] = None
    else:
        base["chg_1d_pct"] = pct_change(vals, 1)
        base["chg_5d_pct"] = pct_change(vals, 5)
    return base


def compute_snapshot(
    metrics_by_name: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    names = (
        "gold_xauusd",
        "us_10y_real_yield",
        "us_10y_nominal_yield",
        "us_10y_breakeven_inflation",
        "usd_cny",
        "dxy",
        "etf_159934_close",
    )
    out: dict[str, Any] = {}
    for name in names:
        obs = load_recent_observations(name, 30, root=root)
        # Include current in-memory point if it advances observation_date
        current = metrics_by_name.get(name)
        if current is not None:
            val = getattr(current, "value", None)
            if val is None and isinstance(current, dict):
                val = current.get("value")
            obs_date = getattr(current, "observation_date", None)
            if obs_date is None and isinstance(current, dict):
                obs_date = current.get("observation_date")
            if val is not None and obs_date:
                if not obs or obs[0]["observation_date"] != obs_date:
                    # Prepend only if new observation_date
                    if not any(o["observation_date"] == obs_date for o in obs):
                        obs = [
                            {
                                "observation_date": obs_date,
                                "value": float(val),
                                "report_date": None,
                                "fetched_at_utc": getattr(current, "fetched_at_utc", None),
                            }
                        ] + obs
                        obs.sort(key=lambda x: x["observation_date"], reverse=True)
        out[name] = compute_metric_change(name, obs)
    return out
