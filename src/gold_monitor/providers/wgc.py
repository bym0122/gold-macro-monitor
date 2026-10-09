"""World Gold Council ETF flows — optional, never blocks daily analysis.

No manual CSV requirement. If no reliable auto source → explicit missing
("暂无最新 WGC 数据"). Never treat stale monthly data as today's flow.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import MetricPoint, DataStatus


class WgcProvider:
    PORTAL = "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows"

    def get_etf_snapshot(self) -> list[MetricPoint]:
        now = datetime.now(timezone.utc).isoformat()
        # Intentionally no fragile HTML scrape as sole path.
        # When a stable free machine-readable endpoint exists, plug in here.
        note = (
            "暂无最新 WGC 自动数据；WGC 非每日硬依赖。"
            "勿将上月流量解释为今日流入。门户: " + self.PORTAL
        )
        return [
            MetricPoint(
                metric="wgc_global_etf_holdings_t",
                value=None,
                unit="tonnes",
                source="WGC",
                source_url=self.PORTAL,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.MISSING,
                notes=note,
            ),
            MetricPoint(
                metric="wgc_global_etf_flow_usd_mn",
                value=None,
                unit="USD million",
                source="WGC",
                source_url=self.PORTAL,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.MISSING,
                notes=note,
            ),
        ]
