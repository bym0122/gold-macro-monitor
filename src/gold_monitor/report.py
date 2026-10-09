"""Markdown daily report: market snapshot + news inventory (no causal analysis)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .providers.base import MetricPoint, DataStatus

# Markdown preview limit; full list always in data/news/YYYY-MM-DD.json
MD_NEWS_PREVIEW_LIMIT = 80


def _fmt_value(p: MetricPoint) -> str:
    if p.value is None:
        return f"— ({p.status.value})"
    if p.unit == "percent":
        return f"{p.value:.3f}% ({p.status.value})"
    if p.unit == "USD" and abs(p.value) > 1e9:
        return f"{p.value/1e12:.3f}T USD ({p.status.value})"
    if p.unit == "contracts":
        return f"{p.value:,.0f} ({p.status.value})"
    if isinstance(p.value, float):
        return f"{p.value:,.2f} {p.unit} ({p.status.value})"
    return f"{p.value} {p.unit} ({p.status.value})"


def _chg_note(indicators: dict[str, Any], metric: str, kind: str = "pct") -> str:
    snap = indicators.get(metric) or {}
    pts = snap.get("history_points") or 0
    chg = snap.get("chg_1d_pct")
    if pts < 2 or chg is None:
        return "相对上一观测：历史不足 / 本次未计算"
    if kind == "yield":
        # chg_1d_pct on yield levels is relative %; also show approx bp if level known
        return f"相对上一有效观测约 {chg:+.2f}%（相对变化；非基点绝对值）"
    return f"相对上一有效观测约 {chg:+.2f}%"


def build_daily_report(
    report_date: str,
    metrics: list[MetricPoint],
    run_id: str,
    indicators: dict[str, Any] | None = None,
    news_articles: list[dict[str, Any]] | None = None,
    news_stats: dict[str, Any] | None = None,
    quality_notes: list[str] | None = None,
    news_json_path: str | None = None,
) -> str:
    by_metric = {m.metric: m for m in metrics}
    now = datetime.now(timezone.utc).isoformat()
    indicators = indicators or {}
    news_articles = news_articles or []
    news_stats = news_stats or {}
    quality_notes = quality_notes or []

    lines = [
        f"# 黄金宏观数据日报 {report_date}",
        "",
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`  ·  schema **v0.5**",
        ">",
        "> **职责边界**：本报告仅含市场数据快照与新闻采集清单。",
        "> 不包含事件聚类、黄金利多/利空判定或 most_likely 因果结论（由后续 ChatGPT 阅读 `data/news/` 完成）。",
        "",
        "## A. 今日市场数据快照",
        "",
        "| 指标 | 最新值 | 观测日 | 采集时间(UTC) | 来源 | 相对变化 | 状态 |",
        "|------|--------|--------|---------------|------|----------|------|",
    ]

    order = [
        ("gold_xauusd", "现货黄金 XAU/USD", "price"),
        ("dxy", "美元指数 DXY", "price"),
        ("dxy_change_pct", "DXY 日变动(源内)", "price"),
        ("etf_159934_close", "159934 场内价", "price"),
        ("etf_159934_change_pct", "159934 涨跌幅", "price"),
        ("usd_cny", "美元兑人民币", "price"),
        ("us_10y_real_yield", "美债 10Y 实际收益率", "yield"),
        ("us_10y_nominal_yield", "美债 10Y 名义收益率", "yield"),
        ("us_10y_breakeven_inflation", "10Y 盈亏平衡通胀", "yield"),
        ("cot_gold_net_noncommercial", "COT 净非商业（周）", "other"),
        ("cot_gold_open_interest", "COT 未平仓（周）", "other"),
        ("us_total_public_debt", "美国公共债务总额", "other"),
        ("us_interest_expense_fytd", "美国利息支出 FYTD", "other"),
        ("wgc_global_etf_holdings_t", "WGC ETF 持仓（可选）", "other"),
    ]

    for key, label, kind in order:
        p = by_metric.get(key)
        if not p:
            lines.append(f"| {label} | — | — | — | — | — | missing |")
            continue
        if key.startswith("wgc_") and p.status != DataStatus.OK:
            lines.append(
                f"| {label} | 暂无最新自动数据 | — | {p.fetched_at_utc[:19] if p.fetched_at_utc else '—'} "
                f"| WGC | — | skipped |"
            )
            continue
        chg = _chg_note(indicators, key, kind)
        # dxy_change_pct already is a day change from provider
        if key == "dxy_change_pct" and p.value is not None:
            chg = f"源内计算 {p.value:+.3f}%"
        fetched = (p.fetched_at_utc or "—")[:19]
        lines.append(
            f"| {label} | {_fmt_value(p)} | {p.observation_date or '—'} "
            f"| {fetched} | [{p.source}]({p.source_url}) | {chg} | {p.status.value} |"
        )

    lines += ["", "### 数据质量提示", ""]
    if quality_notes:
        for n in quality_notes:
            lines.append(f"- {n}")
    else:
        lines.append("- 无额外提示")

    lines += [
        "",
        "## B. 新闻采集总览",
        "",
        f"- 原始拉取条数：**{news_stats.get('raw_fetched', '—')}**",
        f"- 确定性去重后：**{news_stats.get('after_deterministic_dedupe', len(news_articles))}**",
        f"- 精确重复丢弃：**{news_stats.get('exact_dupes_dropped', '—')}**",
        f"- 仅 RSS 摘要：**{news_stats.get('rss_summary_only', '—')}**",
        f"- 全文可用：**{news_stats.get('full_text_available', 0)}**",
        f"- 真实媒体名未确认：**{news_stats.get('unknown_source_name', '—')}**",
        f"- Google News 跳转 URL：**{news_stats.get('google_news_redirect_urls', '—')}**",
        f"- 回溯窗口：{news_stats.get('lookback_hours', '—')} 小时",
        f"- 单源上限：{news_stats.get('per_feed_cap', '—')}",
        "",
        "**以上数字仅描述采集覆盖，不是独立事件数，也不代表市场重要性。**",
        "",
    ]

    failed = news_stats.get("failed_feeds") or []
    if failed:
        lines.append("### 失败信息源")
        for f in failed:
            lines.append(f"- `{f}`")
        lines.append("")

    per_topic = news_stats.get("per_topic_counts") or {}
    if per_topic:
        lines.append("### 各主题拉取计数（去重前）")
        for k, v in sorted(per_topic.items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
        lines.append("")

    per_feed = news_stats.get("per_feed_counts") or {}
    if per_feed:
        lines.append("### 各 Feed 拉取计数（去重前）")
        for k, v in sorted(per_feed.items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
        lines.append("")

    news_link = news_json_path or f"data/news/{report_date}.json"
    lines += [
        "## C. 新闻清单",
        "",
        f"完整新闻 JSON（供 ChatGPT 读取）：[`{news_link}`](../{news_link})",
        "",
        f"Markdown 预览最多 **{MD_NEWS_PREVIEW_LIMIT}** 条；未展示条目仍在 JSON 中，不会静默丢弃。",
        "",
    ]

    known = [a for a in news_articles if a.get("published_at")]
    unknown = [a for a in news_articles if not a.get("published_at")]
    known = sorted(known, key=lambda a: a.get("published_at") or "", reverse=True)

    def _emit_table(rows: list[dict[str, Any]], title: str) -> None:
        lines.append(f"### {title}")
        if not rows:
            lines.append("（无）")
            lines.append("")
            return
        lines.append("| 发布时间 | 标题 | 真实来源 | 主题/Feed | 摘要 | 链接 | 正文状态 |")
        lines.append("|----------|------|----------|-----------|------|------|----------|")
        for a in rows[:MD_NEWS_PREVIEW_LIMIT]:
            pub = (a.get("published_at") or "未知")[:16]
            title_s = (a.get("title") or "").replace("|", "/")[:120]
            src = a.get("source_name") or "未确认"
            topic = a.get("search_topic") or a.get("source_feed") or "—"
            summary = (a.get("summary") or "").replace("|", "/")[:100]
            url = a.get("original_url") or ""
            flag = "⚠跳转" if a.get("url_is_google_news_redirect") else "原文"
            status = a.get("content_status") or "—"
            lines.append(
                f"| {pub} | {title_s} | {src} | {topic} | {summary} "
                f"| [{flag}]({url}) | {status} |"
            )
        if len(rows) > MD_NEWS_PREVIEW_LIMIT:
            lines.append("")
            lines.append(
                f"> 另有 **{len(rows) - MD_NEWS_PREVIEW_LIMIT}** 条仅在 JSON 中，见 `{news_link}`。"
            )
        lines.append("")

    _emit_table(known, "有发布时间（倒序）")
    _emit_table(unknown, "发布时间未知")

    lines += [
        "## D. 原始数据路径",
        "",
        f"- 市场指标：`data/daily/YYYY/MM/{report_date}.json`",
        f"- 完整新闻：`{news_link}`",
        f"- 本报告：`reports/{report_date}.md`",
        "",
        "## 声明",
        "",
        "数据采集与整理自动化；新闻事件识别、交叉验证与黄金影响分析不在本流水线内。",
        "不构成投资建议。",
        "",
    ]
    return "\n".join(lines)
