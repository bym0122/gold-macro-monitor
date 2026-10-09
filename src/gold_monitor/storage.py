"""Persist daily JSON and reports under data/ and reports/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dirs(report_date: str) -> tuple[Path, Path]:
    """report_date: YYYY-MM-DD"""
    y, m, _ = report_date.split("-")
    data_dir = Path("data") / "daily" / y / m
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, reports_dir


def write_daily_json(report_date: str, payload: dict[str, Any]) -> Path:
    data_dir, _ = ensure_dirs(report_date)
    path = data_dir / f"{report_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_report_md(report_date: str, markdown: str) -> Path:
    _, reports_dir = ensure_dirs(report_date)
    path = reports_dir / f"{report_date}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
