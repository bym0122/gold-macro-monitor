"""US Dollar Index via Yahoo Finance DX-Y.NYB (ICE futures-based DXY proxy)."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import MetricPoint, DataStatus


class DxyProvider:
    """Daily DXY-level dollar strength for gold macro cross-checks.

    Validated 2026-10-09: Yahoo chart DX-Y.NYB returns regularMarketPrice.
    Note: this is the futures-linked dollar index quote, not a custom basket.
    """

    URL = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"

    def get_dxy(self) -> list[MetricPoint]:
        now = datetime.now(timezone.utc).isoformat()
        source_url = self.URL + "?interval=1d&range=5d"
        try:
            resp = requests.get(
                self.URL,
                params={"interval": "1d", "range": "5d"},
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (compatible; gold-macro-monitor/0.3)"},
            )
            resp.raise_for_status()
            result = (resp.json().get("chart") or {}).get("result") or []
            if not result:
                return self._fail(now, source_url, "Empty chart result")
            meta = result[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            rmt = meta.get("regularMarketTime")
            obs_date = None
            if rmt:
                try:
                    obs_date = datetime.fromtimestamp(int(rmt), tz=timezone.utc).date().isoformat()
                except Exception:
                    pass
            points: list[MetricPoint] = []
            if price is None:
                return self._fail(now, source_url, "No regularMarketPrice")
            price_f = float(price)
            points.append(
                MetricPoint(
                    metric="dxy",
                    value=price_f,
                    unit="index",
                    source="Yahoo Finance DX-Y.NYB",
                    source_url=source_url,
                    observation_date=obs_date,
                    fetched_at_utc=now,
                    status=DataStatus.OK,
                    notes="ICE US Dollar Index futures quote via Yahoo",
                )
            )
            if prev is not None:
                try:
                    prev_f = float(prev)
                    if prev_f != 0:
                        chg = (price_f - prev_f) / abs(prev_f) * 100.0
                        points.append(
                            MetricPoint(
                                metric="dxy_change_pct",
                                value=chg,
                                unit="percent",
                                source="Yahoo Finance DX-Y.NYB",
                                source_url=source_url,
                                observation_date=obs_date,
                                fetched_at_utc=now,
                                status=DataStatus.OK,
                                notes=f"vs chartPreviousClose={prev_f}",
                            )
                        )
                except (TypeError, ValueError):
                    pass
            return points
        except Exception as e:
            return self._fail(now, source_url, f"Request failed: {e}")

    def _fail(self, now: str, source_url: str, notes: str) -> list[MetricPoint]:
        return [
            MetricPoint(
                metric="dxy",
                value=None,
                unit="index",
                source="Yahoo Finance DX-Y.NYB",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=notes,
            )
        ]
