"""Unit tests for indicator changes (local fixtures, no network)."""

from __future__ import annotations

import json
from pathlib import Path

from gold_monitor.indicators import (
    abs_change,
    pct_change,
    compute_metric_change,
    load_recent_observations,
    compute_snapshot,
)


def test_pct_change_price():
    assert pct_change([110.0, 100.0], 1) == 10.0
    assert pct_change([100.0], 1) is None


def test_yield_bps_absolute():
    # 2.90 -> 2.95 = +0.05 pp = +5 bps
    vals = [2.95, 2.90]
    d = abs_change(vals, 1)
    assert d is not None
    assert abs(d - 0.05) < 1e-9
    assert abs(d * 100 - 5.0) < 1e-9


def test_compute_metric_change_yield():
    obs = [
        {"observation_date": "2026-10-08", "value": 2.95, "report_date": "2026-10-09"},
        {"observation_date": "2026-10-07", "value": 2.90, "report_date": "2026-10-08"},
    ]
    snap = compute_metric_change("us_10y_real_yield", obs)
    assert snap["kind"] == "yield"
    assert snap["chg_1d_pct"] is None  # must not use relative % for yields
    assert abs(snap["chg_1_obs_pp"] - 0.05) < 1e-9
    assert abs(snap["chg_1_obs_bps"] - 5.0) < 1e-9


def test_compute_metric_change_price():
    obs = [
        {"observation_date": "2026-10-09", "value": 4200.0, "report_date": "2026-10-09"},
        {"observation_date": "2026-10-08", "value": 4000.0, "report_date": "2026-10-08"},
    ]
    snap = compute_metric_change("gold_xauusd", obs)
    assert snap["kind"] == "price"
    assert abs(snap["chg_1d_pct"] - 5.0) < 1e-9
    assert snap["chg_1_obs_bps"] is None


def test_insufficient_history_null():
    obs = [{"observation_date": "2026-10-09", "value": 2.95, "report_date": "2026-10-09"}]
    snap = compute_metric_change("us_10y_real_yield", obs)
    assert snap["history_points"] == 1
    assert snap["chg_1_obs_bps"] is None
    assert snap["chg_1_obs_pp"] is None


def test_duplicate_observation_date_skipped(tmp_path: Path):
    """Same FRED observation_date on two report days must not invent a change."""
    day1 = tmp_path / "2026" / "10"
    day1.mkdir(parents=True)
    payload_a = {
        "report_date": "2026-10-08",
        "metrics": [
            {
                "metric": "us_10y_real_yield",
                "value": 2.92,
                "observation_date": "2026-10-07",
            }
        ],
    }
    payload_b = {
        "report_date": "2026-10-09",
        "metrics": [
            {
                "metric": "us_10y_real_yield",
                "value": 2.92,
                "observation_date": "2026-10-07",  # same obs, re-fetched
            }
        ],
    }
    (day1 / "2026-10-08.json").write_text(json.dumps(payload_a), encoding="utf-8")
    (day1 / "2026-10-09.json").write_text(json.dumps(payload_b), encoding="utf-8")

    obs = load_recent_observations("us_10y_real_yield", root=tmp_path)
    assert len(obs) == 1  # deduped by observation_date
    snap = compute_metric_change("us_10y_real_yield", obs)
    assert snap["chg_1_obs_bps"] is None
