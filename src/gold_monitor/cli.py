"""CLI entry for daily / manual runs."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running as python -m gold_monitor.cli from repo root
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from gold_monitor.providers.fred import FredProvider
from gold_monitor.providers.gold_price import GoldPriceProvider
from gold_monitor.providers.china_etf import ChinaGoldETFProvider
from gold_monitor.normalize import normalize_metrics
from gold_monitor.validate import summarize_statuses
from gold_monitor.storage import write_daily_json, write_report_md
from gold_monitor.report import build_daily_report


def run_daily(report_date: str | None = None) -> int:
    report_date = report_date or date.today().isoformat()
    run_id = str(uuid.uuid4())[:8]
    print(f"[gold-monitor] run_id={run_id} report_date={report_date}")

    metrics = []

    # FRED core rates
    fred = FredProvider(config_path=str(ROOT / "config" / "sources.yaml"))
    metrics.extend(fred.get_core_rates())

    # Gold price (placeholder until validated)
    gold = GoldPriceProvider()
    metrics.append(gold.get_spot_or_futures())

    # 159934 (placeholder)
    etf = ChinaGoldETFProvider()
    metrics.extend(etf.get_159934())

    payload = {
        "run_id": run_id,
        "report_date": report_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": normalize_metrics(metrics),
        "status_summary": summarize_statuses(metrics),
        "version": "0.1.0",
    }

    json_path = write_daily_json(report_date, payload)
    md = build_daily_report(report_date, metrics, run_id)
    md_path = write_report_md(report_date, md)

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print("Status summary:", payload["status_summary"])

    # Exit non-zero only on total failure of critical path if desired;
    # for now always 0 so Actions can still commit partial results.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="gold-macro-monitor CLI")
    sub = parser.add_subparsers(dest="cmd")
    daily = sub.add_parser("daily", help="Run daily collection & report")
    daily.add_argument("--date", help="Report date YYYY-MM-DD (default today)")
    args = parser.parse_args()

    if args.cmd == "daily":
        raise SystemExit(run_daily(args.date))
    parser.print_help()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
