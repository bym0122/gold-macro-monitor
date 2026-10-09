"""FRED API provider for core macro series."""

from __future__ import annotations

import os
from datetime import datetime, timezone, date, timedelta
from typing import Any, Optional

import requests
import yaml

from .base import MetricPoint, DataStatus


class FredProvider:
    """Fetch series from FRED. Requires FRED_API_KEY env var."""

    def __init__(self, config_path: str = "config/sources.yaml"):
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.base_url = cfg["fred"]["base_url"].rstrip("/")
        self.series_cfg = cfg["fred"]["series"]
        self.api_key = os.environ.get("FRED_API_KEY", "").strip()

    def _fetch_series_latest(self, series_id: str) -> Optional[dict[str, Any]]:
        if not self.api_key:
            return None
        url = f"{self.base_url}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 5,
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        observations = data.get("observations") or []
        for obs in observations:
            val = obs.get("value")
            if val is not None and val != ".":
                return obs
        return None

    def get_metric(self, series_id: str) -> MetricPoint:
        meta = self.series_cfg.get(series_id)
        if not meta:
            return MetricPoint.missing(
                metric=series_id,
                unit="",
                source="FRED",
                source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                notes=f"Series {series_id} not configured",
            )

        metric = meta["metric"]
        unit = meta.get("unit", "percent")
        source_url = f"https://fred.stlouisfed.org/series/{series_id}"
        expected_lag = int(meta.get("expected_lag_days", 2))

        if not self.api_key:
            return MetricPoint.missing(
                metric=metric,
                unit=unit,
                source="FRED",
                source_url=source_url,
                notes="FRED_API_KEY not set",
            )

        try:
            obs = self._fetch_series_latest(series_id)
        except Exception as e:
            return MetricPoint(
                metric=metric,
                value=None,
                unit=unit,
                source="FRED",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                status=DataStatus.INVALID,
                notes=f"Request failed: {e}",
            )

        if not obs:
            return MetricPoint.missing(
                metric=metric,
                unit=unit,
                source="FRED",
                source_url=source_url,
                notes="No valid observation returned",
            )

        try:
            value = float(obs["value"])
        except (TypeError, ValueError):
            return MetricPoint(
                metric=metric,
                value=None,
                unit=unit,
                source="FRED",
                source_url=source_url,
                observation_date=obs.get("date"),
                fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                status=DataStatus.INVALID,
                notes=f"Cannot parse value: {obs.get('value')}",
            )

        obs_date_str = obs.get("date")
        status = DataStatus.OK
        notes = ""
        if obs_date_str:
            try:
                obs_date = date.fromisoformat(obs_date_str)
                age = (date.today() - obs_date).days
                if age > expected_lag + 1:
                    status = DataStatus.STALE
                    notes = f"Observation age {age}d exceeds expected lag {expected_lag}d"
            except ValueError:
                notes = f"Unparseable observation date: {obs_date_str}"

        return MetricPoint(
            metric=metric,
            value=value,
            unit=unit,
            source="FRED",
            source_url=source_url,
            observation_date=obs_date_str,
            fetched_at_utc=datetime.now(timezone.utc).isoformat(),
            status=status,
            notes=notes,
        )

    def get_core_rates(self) -> list[MetricPoint]:
        results = []
        for series_id in ("DFII10", "DGS10", "T10YIE"):
            results.append(self.get_metric(series_id))
        return results
