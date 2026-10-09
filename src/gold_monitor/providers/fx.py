"""USD/CNY via Yahoo Finance CNY=X."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import MetricPoint, DataStatus


class FxProvider:
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/CNY=X"

    def get_usd_cny(self) -> MetricPoint:
        now = datetime.now(timezone.utc).isoformat()
        source_url = self.URL + "?interval=1d&range=5d"
        try:
            resp = requests.get(
                self.URL,
                params={"interval": "1d", "range": "5d"},
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (compatible; gold-macro-monitor/0.1)"},
            )
            resp.raise_for_status()
            result = (resp.json().get("chart") or {}).get("result") or []
            if not result:
                return MetricPoint.missing(
                    "usd_cny", "CNY per USD", "Yahoo Finance", source_url, "Empty result"
                )
            meta = result[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            rmt = meta.get("regularMarketTime")
            obs_date = None
            if rmt:
                try:
                    obs_date = datetime.fromtimestamp(int(rmt), tz=timezone.utc).date().isoformat()
                except Exception:
                    pass
            value = float(price)
            return MetricPoint(
                metric="usd_cny",
                value=value,
                unit="CNY per USD",
                source="Yahoo Finance",
                source_url=source_url,
                observation_date=obs_date,
                fetched_at_utc=now,
                status=DataStatus.OK,
                notes="CNY=X last; offshore-ish FX quote via Yahoo",
            )
        except Exception as e:
            return MetricPoint(
                metric="usd_cny",
                value=None,
                unit="CNY per USD",
                source="Yahoo Finance",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=f"Request failed: {e}",
            )
