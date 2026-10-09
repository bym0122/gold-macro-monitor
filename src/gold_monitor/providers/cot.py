"""CFTC Gold COT — free CSV from futuresbench (derived from public CFTC data)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import requests

from .base import MetricPoint, DataStatus


class CotProvider:
    """Weekly gold COT net noncommercial / commercial / OI.

    Source CSV: https://futuresbench.com/data/cot/gold.csv
    Columns: report_date, open_interest, net_noncommercial, net_commercial, ...
    Always record report_date (positions as-of Tuesday), not fetch day.
    """

    CSV_URL = "https://futuresbench.com/data/cot/gold.csv"

    def get_latest(self) -> list[MetricPoint]:
        now = datetime.now(timezone.utc).isoformat()
        try:
            resp = requests.get(
                self.CSV_URL,
                timeout=30,
                headers={"User-Agent": "gold-macro-monitor/0.1"},
            )
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
            if not rows:
                return self._empty(now, "Empty CSV")
            # last row is latest
            last = rows[-1]
            report_date = last.get("report_date")
            points = []
            for field, metric, unit in (
                ("open_interest", "cot_gold_open_interest", "contracts"),
                ("net_noncommercial", "cot_gold_net_noncommercial", "contracts"),
                ("net_commercial", "cot_gold_net_commercial", "contracts"),
            ):
                raw = last.get(field)
                try:
                    val = float(raw)
                    points.append(
                        MetricPoint(
                            metric=metric,
                            value=val,
                            unit=unit,
                            source="CFTC via futuresbench",
                            source_url=self.CSV_URL,
                            observation_date=report_date,
                            fetched_at_utc=now,
                            status=DataStatus.OK,
                            notes=f"positions as-of {report_date}; weekly COT; not same-day",
                        )
                    )
                except (TypeError, ValueError):
                    points.append(
                        MetricPoint(
                            metric=metric,
                            value=None,
                            unit=unit,
                            source="CFTC via futuresbench",
                            source_url=self.CSV_URL,
                            observation_date=report_date,
                            fetched_at_utc=now,
                            status=DataStatus.INVALID,
                            notes=f"Cannot parse {field}={raw}",
                        )
                    )
            return points
        except Exception as e:
            return self._empty(now, f"Request failed: {e}")

    def _empty(self, now: str, notes: str) -> list[MetricPoint]:
        out = []
        for metric, unit in (
            ("cot_gold_open_interest", "contracts"),
            ("cot_gold_net_noncommercial", "contracts"),
            ("cot_gold_net_commercial", "contracts"),
        ):
            out.append(
                MetricPoint(
                    metric=metric,
                    value=None,
                    unit=unit,
                    source="CFTC via futuresbench",
                    source_url=self.CSV_URL,
                    observation_date=None,
                    fetched_at_utc=now,
                    status=DataStatus.INVALID,
                    notes=notes,
                )
            )
        return out
