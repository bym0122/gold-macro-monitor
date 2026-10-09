"""Gold price provider — primary: goldprice.dev (no key, XAU-USD spot)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import requests

from .base import MetricPoint, DataStatus


class GoldPriceProvider:
    """Validated free source: https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT

    Terms: anonymous free tier for internal use; check is_stale; record computed_at.
    Tested 2026-10-09: returns price, is_stale, computed_at.
    """

    PRIMARY_URL = "https://api.goldprice.dev/v1/prices"

    def __init__(self, primary: str = "goldprice_dev"):
        self.primary = primary

    def get_spot_or_futures(self) -> MetricPoint:
        now = datetime.now(timezone.utc).isoformat()
        source_url = f"{self.PRIMARY_URL}?symbol=XAU-USD-SPOT"
        try:
            resp = requests.get(
                self.PRIMARY_URL,
                params={"symbol": "XAU-USD-SPOT"},
                timeout=20,
                headers={"User-Agent": "gold-macro-monitor/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
            symbols = data.get("symbols") or []
            if not symbols:
                return MetricPoint.missing(
                    metric="gold_xauusd",
                    unit="USD/oz",
                    source="goldprice.dev",
                    source_url=source_url,
                    notes="Empty symbols array",
                )
            s = symbols[0]
            price_raw = s.get("price")
            is_stale = bool(s.get("is_stale"))
            computed_at = s.get("computed_at") or ""
            try:
                value = float(price_raw)
            except (TypeError, ValueError):
                return MetricPoint(
                    metric="gold_xauusd",
                    value=None,
                    unit="USD/oz",
                    source="goldprice.dev",
                    source_url=source_url,
                    observation_date=None,
                    fetched_at_utc=now,
                    status=DataStatus.INVALID,
                    notes=f"Cannot parse price: {price_raw}",
                )
            # observation date from computed_at
            obs_date = None
            if computed_at:
                try:
                    obs_date = computed_at[:10]
                except Exception:
                    pass
            status = DataStatus.STALE if is_stale else DataStatus.OK
            notes = f"contract_type={s.get('contract_type')}; computed_at={computed_at}"
            if is_stale:
                notes += "; source marked is_stale=true"
            return MetricPoint(
                metric="gold_xauusd",
                value=value,
                unit="USD/oz",
                source="goldprice.dev",
                source_url=source_url,
                observation_date=obs_date,
                fetched_at_utc=now,
                status=status,
                notes=notes,
            )
        except Exception as e:
            return MetricPoint(
                metric="gold_xauusd",
                value=None,
                unit="USD/oz",
                source="goldprice.dev",
                source_url=source_url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=f"Request failed: {e}",
            )
