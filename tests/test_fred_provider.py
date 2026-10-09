"""Unit tests for FredProvider – use mocks, never hit live API in CI."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from gold_monitor.providers.fred import FredProvider
from gold_monitor.providers.base import DataStatus


@pytest.fixture
def provider(tmp_path):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(
        """
fred:
  base_url: "https://api.stlouisfed.org/fred"
  series:
    DFII10:
      metric: us_10y_real_yield
      unit: percent
      expected_lag_days: 2
    DGS10:
      metric: us_10y_nominal_yield
      unit: percent
      expected_lag_days: 1
    T10YIE:
      metric: us_10y_breakeven_inflation
      unit: percent
      expected_lag_days: 1
""",
        encoding="utf-8",
    )
    return FredProvider(config_path=str(cfg))


def test_missing_api_key(provider):
    with patch.dict(os.environ, {}, clear=True):
        provider.api_key = ""
        p = provider.get_metric("DFII10")
        assert p.status == DataStatus.MISSING
        assert "FRED_API_KEY" in p.notes


def test_successful_fetch(provider):
    mock_obs = {"date": "2026-10-08", "value": "1.72"}
    with patch.object(provider, "_fetch_series_latest", return_value=mock_obs):
        provider.api_key = "dummy"
        p = provider.get_metric("DFII10")
        assert p.status in (DataStatus.OK, DataStatus.STALE)
        assert p.value == 1.72
        assert p.observation_date == "2026-10-08"
        assert p.metric == "us_10y_real_yield"


def test_invalid_value(provider):
    mock_obs = {"date": "2026-10-08", "value": "N/A"}
    with patch.object(provider, "_fetch_series_latest", return_value=mock_obs):
        provider.api_key = "dummy"
        p = provider.get_metric("DFII10")
        assert p.status == DataStatus.INVALID
        assert p.value is None
