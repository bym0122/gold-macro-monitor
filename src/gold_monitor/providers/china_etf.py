"""China Gold ETF 159934 via Yahoo Finance chart API (public, no key)."""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Optional

import requests

from .base import MetricPoint, DataStatus


class ChinaGoldETFProvider:
    """159934.SZ market price via Yahoo chart endpoint.

    Tested 2026-10-09: returns regularMarketPrice, change %, volume, timestamps.
    Note: this is exchange close/last price, NOT fund NAV. Do not mix with NAV for premium
    unless both have matching timestamps.
    """

    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/159934.SZ"

    def get_159934(self) -> list[MetricPoint]:
        now = datetime.now(timezone.utc).isoformat()
        source_url = self.CHART_URL + "?interval=1d&range=5d"
        try:
            resp = requests.get(
                self.CHART_URL,
                params={"interval": "1d", "range": "5d"},
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (compatible; gold-macro-monitor/0.1)"},
            )
            resp.raise_for_status()
            data = resp.json()
            result = (data.get("chart") or {}).get("result") or []
            if not result:
                return self._missing_pair(now, source_url, "Empty chart result")
            meta = result[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            chg_pct = meta.get("regularMarketChangePercent")
            rmt = meta.get("regularMarketTime")
            obs_date = None
            if rmt:
                try:
                    obs_date = datetime.fromtimestamp(int(rmt), tz=timezone.utc).date().isoformat()
                except Exception:
                    pass
            points = []
            if price is not None:
                try:
                    price_f = float(price)
                    points.append(
                        MetricPoint(
                            metric="etf_159934_close",
                            value=price_f,
                            unit="CNY",
                            source="Yahoo Finance",
                            source_url=source_url,
                            observation_date=obs_date,
                            fetched_at_utc=now,
                            status=DataStatus.OK,
                            notes="exchange last/close; not fund NAV",
                        )
                    )
                except (TypeError, ValueError):
                    points.append(
                        MetricPoint(
                            metric="etf_159934_close",
                            value=None,
                            unit="CNY",
                            source="Yahoo Finance",
                            source_url=source_url,
                            observation_date=obs_date,
                            fetched_at_utc=now,
                            status=DataStatus.INVALID,
                            notes=f"Cannot parse price: {price}",
                        )
                    )
            else:
                points.append(
                    MetricPoint.missing(
                        "etf_159934_close", "CNY", "Yahoo Finance", source_url, "No price in meta"
                    )
                )

            if chg_pct is not None:
                try:
                    chg_f = float(chg_pct)
                    points.append(
                        MetricPoint(
                            metric="etf_159934_change_pct",
                            value=chg_f,
                            unit="percent",
                            source="Yahoo Finance",
                            source_url=source_url,
                            observation_date=obs_date,
                            fetched_at_utc=now,
                            status=DataStatus.OK,
                            notes="regularMarketChangePercent",
                        )
                    )
                except (TypeError, ValueError):
                    points.append(
                        MetricPoint(
                            metric="etf_159934_change_pct",
                            value=None,
                            unit="percent",
                            source="Yahoo Finance",
                            source_url=source_url,
                            observation_date=obs_date,
                            fetched_at_utc=now,
                            status=DataStatus.INVALID,
                            notes=f"Cannot parse change%: {chg_pct}",
                        )
                    )
            else:
                points.append(
                    MetricPoint.missing(
                        "etf_159934_change_pct",
                        "percent",
                        "Yahoo Finance",
                        source_url,
                        "No change percent in meta",
                    )
                )
            return points
        except Exception as e:
            return self._missing_pair(now, source_url, f"Request failed: {e}")

    def _missing_pair(self, now: str, source_url: str, notes: str) -> list[MetricPoint]:
        return [
            MetricPoint(
                metric="etf_159934_close",
                value=None,
                unit="CNY",
                source="Yahoo Finance",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=notes,
            ),
            MetricPoint(
                metric="etf_159934_change_pct",
                value=None,
                unit="percent",
                source="Yahoo Finance",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=notes,
            ),
        ]
