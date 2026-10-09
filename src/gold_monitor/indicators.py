"""Simple reproducible indicators from metric history (JSON files)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def load_recent_metric_values(metric: str, max_days: int = 90) -> list[tuple[str, float]]:
    root = Path("data/daily")
    if not root.exists():
        return []
    pairs: list[tuple[str, float]] = []
    files = sorted(root.rglob("*.json"), reverse=True)
    for fp in files[:max_days]:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
            for m in payload.get("metrics") or []:
                if m.get("metric") == metric and m.get("value") is not None:
                    pairs.append((payload.get("report_date") or fp.stem, float(m["value"])))
                    break
        except Exception:
            continue
    return pairs


def pct_change(values: list[float], lag: int) -> Optional[float]:
    if len(values) <= lag:
        return None
    a, b = values[0], values[lag]
    if b == 0:
        return None
    return (a - b) / abs(b) * 100.0


def compute_snapshot(metrics_by_name: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in (
        "gold_xauusd",
        "us_10y_real_yield",
        "us_10y_nominal_yield",
        "usd_cny",
        "dxy",
    ):
        hist = load_recent_metric_values(name, 30)
        vals = [v for _, v in hist]
        out[name] = {
            "history_points": len(vals),
            "chg_1d_pct": pct_change(vals, 1) if len(vals) > 1 else None,
            "chg_5d_pct": pct_change(vals, 5) if len(vals) > 5 else None,
        }
    return out
