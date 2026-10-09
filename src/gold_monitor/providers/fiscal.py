"""US Treasury FiscalData — debt to the penny + interest expense (no API key)."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import MetricPoint, DataStatus

BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


class FiscalProvider:
    def get_debt_to_penny(self) -> MetricPoint:
        now = datetime.now(timezone.utc).isoformat()
        url = f"{BASE}/v2/accounting/od/debt_to_penny"
        params = {"sort": "-record_date", "page[size]": "1"}
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            rows = resp.json().get("data") or []
            if not rows:
                return MetricPoint.missing(
                    "us_total_public_debt",
                    "USD",
                    "FiscalData",
                    url,
                    "No rows",
                )
            row = rows[0]
            value = float(row["tot_pub_debt_out_amt"])
            return MetricPoint(
                metric="us_total_public_debt",
                value=value,
                unit="USD",
                source="FiscalData",
                source_url="https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny",
                observation_date=row.get("record_date"),
                fetched_at_utc=now,
                status=DataStatus.OK,
                notes=f"debt_held_public={row.get('debt_held_public_amt')}; intragov={row.get('intragov_hold_amt')}",
            )
        except Exception as e:
            return MetricPoint(
                metric="us_total_public_debt",
                value=None,
                unit="USD",
                source="FiscalData",
                source_url=url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=f"Request failed: {e}",
            )

    def get_interest_expense_fytd(self) -> MetricPoint:
        """Sum FYTD interest expense lines for latest month available."""
        now = datetime.now(timezone.utc).isoformat()
        url = f"{BASE}/v2/accounting/od/interest_expense"
        params = {"sort": "-record_date", "page[size]": "50"}
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            rows = resp.json().get("data") or []
            if not rows:
                return MetricPoint.missing(
                    "us_interest_expense_fytd",
                    "USD",
                    "FiscalData",
                    url,
                    "No rows",
                )
            latest_date = rows[0].get("record_date")
            total = 0.0
            for r in rows:
                if r.get("record_date") != latest_date:
                    break
                try:
                    total += float(r.get("fytd_expense_amt") or 0)
                except (TypeError, ValueError):
                    pass
            return MetricPoint(
                metric="us_interest_expense_fytd",
                value=total,
                unit="USD",
                source="FiscalData",
                source_url="https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/",
                observation_date=latest_date,
                fetched_at_utc=now,
                status=DataStatus.OK,
                notes="sum of fytd_expense_amt for latest record_date lines; monthly lag",
            )
        except Exception as e:
            return MetricPoint(
                metric="us_interest_expense_fytd",
                value=None,
                unit="USD",
                source="FiscalData",
                source_url=url,
                observation_date=None,
                fetched_at_utc=now,
                status=DataStatus.INVALID,
                notes=f"Request failed: {e}",
            )
