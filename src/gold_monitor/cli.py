"""CLI: collect market metrics + news inventory + official calendar; no causal news analysis."""

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
from gold_monitor.providers.dxy import DxyProvider
from gold_monitor.providers.cot import CotProvider
from gold_monitor.providers.fiscal import FiscalProvider
from gold_monitor.providers.wgc import WgcProvider
from gold_monitor.providers.news import NewsProvider
from gold_monitor.normalize import normalize_metrics
from gold_monitor.validate import summarize_statuses
from gold_monitor.storage import write_daily_json, write_news_json, write_report_md
from gold_monitor.report import build_daily_report
from gold_monitor.indicators import compute_snapshot
from gold_monitor.explain import data_quality_notes
from gold_monitor.providers.base import MetricPoint
from gold_monitor.calendar_collect import collect_calendar


def _collect_daily() -> list[MetricPoint]:
    metrics: list[MetricPoint] = []
    fred = FredProvider(config_path=str(ROOT / "config" / "sources.yaml"))
    metrics.extend(fred.get_core_rates())
    metrics.append(GoldPriceProvider().get_spot_or_futures())
    metrics.extend(ChinaGoldETFProvider().get_159934())
    metrics.append(FxProvider().get_usd_cny())
    metrics.extend(DxyProvider().get_dxy())
    return metrics


def _collect_weekly_extras() -> list[MetricPoint]:
    metrics: list[MetricPoint] = []
    metrics.extend(CotProvider().get_latest())
    metrics.extend(WgcProvider().get_etf_snapshot())
    return metrics


def _collect_monthly_extras() -> list[MetricPoint]:
    fiscal = FiscalProvider()
    return [fiscal.get_debt_to_penny(), fiscal.get_interest_expense_fytd()]


def run_daily(report_date: str | None = None) -> int:
    report_date = report_date or date.today().isoformat()
    run_id = str(uuid.uuid4())[:8]
    print(f"[gold-monitor] run_id={run_id} report_date={report_date} schema=v0.9")

    metrics = _collect_daily()
    metrics.extend(_collect_weekly_extras())
    metrics.extend(_collect_monthly_extras())

    calendar_path = None
    calendar_payload = None
    try:
        cal = collect_calendar(root=Path("."))
        calendar_path = cal["path"]
        calendar_payload = cal["payload"]
        st = calendar_payload.get("collection_stats") or {}
        print(
            f"[gold-monitor] calendar merged={st.get('merged_total')} "
            f"upcoming_7d={st.get('upcoming_7d_count')} errors={st.get('errors')}"
        )
    except Exception as e:
        print(f"[gold-monitor] calendar collect failed: {e}")

    news_result = None
    try:
        news_result = NewsProvider().collect()
        print(
            f"[gold-monitor] news raw={news_result.stats.get('raw_count')} "
            f"deduped={news_result.stats.get('after_deterministic_dedupe')} "
            f"trunc={news_result.stats.get('possible_truncation_any')} "
            f"feeds={len(news_result.stats.get('feeds') or [])}"
        )
    except Exception as e:
        print(f"[gold-monitor] news collect failed: {e}")

    articles = [a.to_dict() for a in (news_result.articles if news_result else [])]
    news_stats = (news_result.stats if news_result else {"error": "news collect failed"})

    news_payload = {
        "schema_version": "news_v1",
        "report_date": report_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "articles": articles,
        "collection_stats": news_stats,
    }
    news_path = write_news_json(report_date, news_payload)

    by_name = {m.metric: m for m in metrics}
    ind = compute_snapshot(by_name)
    qnotes = data_quality_notes(by_name, ind)

    daily_payload = {
        "schema_version": "daily_v0.9",
        "run_id": run_id,
        "report_date": report_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": normalize_metrics(metrics),
        "status_summary": summarize_statuses(metrics),
        "indicators": ind,
        "news_ref": str(news_path),
        "calendar_ref": calendar_path,
        "news_collection_stats": news_stats,
        "calendar_stats": (calendar_payload or {}).get("collection_stats"),
        "data_quality_notes": qnotes,
        "version": "0.9.0",
        "analysis": None,
        "explanations": None,
        "events": None,
    }

    json_path = write_daily_json(report_date, daily_payload)
    md = build_daily_report(
        report_date=report_date,
        metrics=metrics,
        run_id=run_id,
        indicators=ind,
        news_articles=articles,
        news_stats=news_stats,
        quality_notes=qnotes,
        news_json_path=str(news_path),
        calendar_payload=calendar_payload,
    )
    md_path = write_report_md(report_date, md)

    print(f"Wrote {json_path}")
    print(f"Wrote {news_path}")
    if calendar_path:
        print(f"Wrote {calendar_path}")
    print(f"Wrote {md_path}")
    print("Status summary:", daily_payload["status_summary"])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="gold-macro-monitor CLI")
    sub = parser.add_subparsers(dest="cmd")
    for name, help_ in (
        ("daily", "Daily collection report"),
        ("weekly", "Weekly emphasis"),
        ("monthly", "Monthly emphasis"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--date", help="Report date YYYY-MM-DD")

    args = parser.parse_args()
    if args.cmd in ("daily", "weekly", "monthly"):
        raise SystemExit(run_daily(getattr(args, "date", None)))
    parser.print_help()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
