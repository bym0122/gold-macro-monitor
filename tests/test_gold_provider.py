"""Smoke tests that hit live free endpoints (may skip on network failure)."""

from __future__ import annotations

import pytest

from gold_monitor.providers.gold_price import GoldPriceProvider
from gold_monitor.providers.china_etf import ChinaGoldETFProvider
from gold_monitor.providers.base import DataStatus


@pytest.mark.integration
def test_gold_live():
    p = GoldPriceProvider().get_spot_or_futures()
    assert p.metric == "gold_xauusd"
    if p.status == DataStatus.OK:
        assert p.value is not None and p.value > 0
    else:
        assert p.status in (DataStatus.STALE, DataStatus.INVALID, DataStatus.MISSING)


@pytest.mark.integration
def test_etf_live():
    pts = ChinaGoldETFProvider().get_159934()
    assert any(p.metric == "etf_159934_close" for p in pts)
