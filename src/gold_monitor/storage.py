"""Persist daily metrics JSON, news JSON, and markdown reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_daily_json(report_date: str, payload: dict[str, Any], root: Path | None = None) -> Path:
    root = root or Path(".")
    y, m, _ = report_date.split("-")
    path = root / "data" / "daily" / y / m / f"{report_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_news_json(report_date: str, payload: dict[str, Any], root: Path | None = None) -> Path:
    """Full news payload for downstream ChatGPT analysis."""
    root = root or Path(".")
    path = root / "data" / "news" / f"{report_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_report_md(report_date: str, markdown: str, root: Path | None = None) -> Path:
    root = root or Path(".")
    path = root / "reports" / f"{report_date}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
