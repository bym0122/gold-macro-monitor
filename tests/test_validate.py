from gold_monitor.providers.base import MetricPoint, DataStatus
from gold_monitor.validate import summarize_statuses, has_critical_missing
from datetime import datetime, timezone


def _mp(metric, status):
    return MetricPoint(
        metric=metric,
        value=None,
        unit="",
        source="t",
        source_url="",
        observation_date=None,
        fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        status=status,
    )


def test_summarize():
    pts = [
        _mp("a", DataStatus.OK),
        _mp("b", DataStatus.MISSING),
        _mp("c", DataStatus.OK),
    ]
    s = summarize_statuses(pts)
    assert s["ok"] == 2
    assert s["missing"] == 1


def test_critical_missing():
    pts = [_mp("us_10y_real_yield", DataStatus.MISSING)]
    assert has_critical_missing(pts, {"us_10y_real_yield"}) is True
    assert has_critical_missing(pts, {"other"}) is False
