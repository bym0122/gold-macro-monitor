"""CLI entry for daily / weekly / monthly runs."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from gold_monitor.providers.fred import FredProvider
from gold_monitor.providers.gold_price import GoldPriceProvider
from gold_monitor.providers.china_etf import ChinaGoldETFProvider
from gold_monitor.providers.fx import FxProvider
from gold_monitor.providers.cot import CotProvider
from gold_monitor.providers.fiscal import FiscalProvider
from gold_monitor.providers.wgc import WgcProvider
from gold_monitor.normalize import normalize_metrics
from gold_monitor.validate import summarize_statuses
from gold_monitor.storage import write_daily_json, write_report_md
from gold_monitor.report import build_daily_report
from gold_monitor.indicators import compute_snapshot
from gold_monitor.explain import candidate_explanations
from gold_monitor.providers.base import MetricPoint


def _collect_daily() -> list[MetricPoint]:
    metrics: list[MetricPoint] = []
    fred = FredProvider(config_path=str(ROOT / "config" / "sources.yaml"))
    metrics.extend(fred.get_core_rates())
    metrics.append(GoldPriceProvider().get_spot_or_futures())
    metrics.extend(ChinaGoldETFProvider().get_159934())
    metrics.append(FxProvider().get_usd_cny())
    return metrics


def _collect_weekly_extras() -> list[MetricPoint]:
    metrics: list[MetricPoint] = []
    metrics.extend(CotProvider().get_latest())
    metrics.extend(WgcProvider().get_etf_snapshot())
    return metrics


def _collect_monthly_extras() -> list[MetricPoint]:
    fiscal = FiscalProvider()
    return [fiscal.get_debt_to_penny(), fiscal.get_interest_expense_fytd()]


def run_daily(report_date: str | None = None, include_weekly: bool = False, include_monthly: bool = False) -> int:
    report_date = report_date or date.today().isoformat()
    run_id = str(uuid.uuid4())[:8]
    print(f"[gold-monitor] run_id={run_id} report_date={report_date}")

    metrics = _collect_daily()
    if include_weekly:
        metrics.extend(_collect_weekly_extras())
    if include_monthly:
        metrics.extend(_collect_monthly_extras())

    # On pure daily runs still attach last-known weekly/monthly if we want fuller report:
    # always try COT/WGC/fiscal so report section is populated (they are lagged data)
    if not include_weekly:
        metrics.extend(_collect_weekly_extras())
    if not include_monthly:
        metrics.extend(_collect_monthly_extras())

    by_name = {m.metric: m for m in metrics}
    ind = compute_snapshot(by_name)
    explanations = candidate_explanations(by_name, ind)

    payload = {
        "run_id": run_id,
        "report_date": report_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": normalize_metrics(metrics),
        "status_summary": summarize_statuses(metrics),
        "indicators": ind,
        "explanations": explanations,
        "version": "0.2.0",
    }

    json_path = write_daily_json(report_date, payload)
    md = build_daily_report(report_date, metrics, run_id, explanations, ind)
    md_path = write_report_md(report_date, md)

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print("Status summary:", payload["status_summary"])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="gold-macro-monitor CLI")
    sub = parser.add_subparsers(dest="cmd")

    daily = sub.add_parser("daily", help="Daily collection & report")
    daily.add_argument("--date", help="Report date YYYY-MM-DD")

    weekly = sub.add_parser("weekly", help="Weekly: COT + WGC + daily core")
    weekly.add_argument("--date", help="Report date YYYY-MM-DD")

    monthly = sub.add_parser("monthly", help="Monthly: fiscal + weekly + daily")
    monthly.add_argument("--date", help="Report date YYYY-MM-DD")

    args = parser.parse_args()
    if args.cmd == "daily":
        raise SystemExit(run_daily(args.date))
    if args.cmd == "weekly":
        raise SystemExit(run_daily(args.date, include_weekly=True))
    if args.cmd == "monthly":
        raise SystemExit(run_daily(args.date, include_weekly=True, include_monthly=True))
    parser.print_help()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
