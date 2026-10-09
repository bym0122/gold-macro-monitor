"""World Gold Council ETF flows — no stable free machine API.

Per design: do not scrape paywalled content; support manual CSV and mark missing.
WGC publishes monthly Excel on gold.org; auto-fetch is best-effort only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv

from .base import MetricPoint, DataStatus

MANUAL_CSV = Path("data/manual/wgc_etf_flows.csv")


class WgcProvider:
    """Prefer manual CSV columns: as_of_month, global_holdings_tonnes, global_flow_usd_mn, notes"""

    def get_etf_snapshot(self) -> list[MetricPoint]:
        now = datetime.now(timezone.utc).isoformat()
        if MANUAL_CSV.exists():
            try:
                with MANUAL_CSV.open(encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                if rows:
                    last = rows[-1]
                    points = []
                    for col, metric, unit in (
                        ("global_holdings_tonnes", "wgc_global_etf_holdings_t", "tonnes"),
                        ("global_flow_usd_mn", "wgc_global_etf_flow_usd_mn", "USD million"),
                    ):
                        raw = last.get(col)
                        try:
                            val = float(raw)
                            points.append(
                                MetricPoint(
                                    metric=metric,
                                    value=val,
                                    unit=unit,
                                    source="WGC manual CSV",
                                    source_url="https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
                                    observation_date=last.get("as_of_month"),
                                    fetched_at_utc=now,
                                    status=DataStatus.OK,
                                    notes=last.get("notes") or "manual entry; monthly lag",
                                )
                            )
                        except (TypeError, ValueError):
                            points.append(
                                MetricPoint.missing(
                                    metric,
                                    unit,
                                    "WGC manual CSV",
                                    "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
                                    f"bad value {raw}",
                                )
                            )
                    return points
            except Exception as e:
                pass
        # No auto source — explicit missing
        return [
            MetricPoint.missing(
                "wgc_global_etf_holdings_t",
                "tonnes",
                "WGC",
                "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
                "No stable free API; place CSV at data/manual/wgc_etf_flows.csv",
            ),
            MetricPoint.missing(
                "wgc_global_etf_flow_usd_mn",
                "USD million",
                "WGC",
                "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
                "No stable free API; place CSV at data/manual/wgc_etf_flows.csv",
            ),
        ]
