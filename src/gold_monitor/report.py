"""Markdown daily report: market snapshot + calendar + news inventory (no causal analysis)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .providers.base import MetricPoint, DataStatus

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
    if pts < 2:
        return "相对上一有效观测：历史不足 / null"

    if kind == "yield":
        bps = snap.get("chg_1_obs_bps")
        pp = snap.get("chg_1_obs_pp")
        prior = snap.get("prior_observation_date")
        latest = snap.get("latest_observation_date")
        if bps is None:
            return "相对上一有效观测：null"
        return (
            f"{bps:+.1f} bps（{pp:+.3f} 百分点；观测 {prior} → {latest}）"
        )

    chg = snap.get("chg_1d_pct")
    if chg is None:
        return "相对上一有效观测：null"
    return f"相对上一有效观测约 {chg:+.2f}%"


def _event_date(ev: dict[str, Any]) -> str:
    return (
        ev.get("scheduled_date")
        or (ev.get("scheduled_at") or "")[:10]
        or ev.get("date")
        or ev.get("start_date")
        or "—"
    )


def _event_name(ev: dict[str, Any]) -> str:
    return (
        ev.get("event_name")
        or ev.get("title")
        or ev.get("name")
        or "—"
    ).replace("|", "/")[:80]


def _render_calendar_section(calendar_payload: dict[str, Any] | None, report_date: str) -> list[str]:
    lines: list[str] = [
        "",
        "## B. 官方经济日历（BLS / BEA / FOMC / 市场结构 / 国债）",
        "",
    ]
    if not calendar_payload:
        lines.append("（本 run 未采集到日历数据）")
        lines.append("")
        return lines

    stats = calendar_payload.get("collection_stats") or {}
    dq = calendar_payload.get("data_quality") or {}
    cal_path = calendar_payload.get("path") or f"data/calendar/{report_date}.json"
    lines += [
        f"- schema：**{calendar_payload.get('schema_version', '—')}**",
        f"- 合并事件总数：**{stats.get('merged_total', '—')}**",
        f"- 未来 7 天：**{stats.get('upcoming_7d_count', '—')}**",
        f"- 近 14 天：**{stats.get('recent_14d_count', '—')}**",
        f"- 来源成功：{', '.join(dq.get('sources_ok') or []) or '—'}",
        f"- 来源部分成功：{', '.join(dq.get('sources_partial') or []) or '无'}",
        f"- 来源失败：{', '.join(dq.get('sources_failed') or []) or '无'}",
        f"- 完整 JSON：[`{cal_path}`](../{cal_path})",
        "",
    ]
    detail = dq.get("source_detail") or stats.get("source_detail") or {}
    if detail:
        lines.append("### 来源明细")
        for k, v in detail.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    errors = stats.get("errors") or []
    if errors:
        lines.append("### 采集错误 / 降级")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    def _emit_events(title: str, key: str) -> None:
        events = calendar_payload.get(key) or []
        lines.append(f"### {title}")
        if not events:
            lines.append("（无）")
            lines.append("")
            return
        lines.append("| 日期 | 事件 | 来源 | 类型 | 数据质量 | 实际值 |")
        lines.append("|------|------|------|------|----------|--------|")
        for ev in events[:40]:
            d = _event_date(ev)
            name = _event_name(ev)
            src = ev.get("source_name") or ev.get("source") or "—"
            subtype = (
                ev.get("event_type")
                or ev.get("event_subtype")
                or ev.get("subtype")
                or "—"
            )
            dqv = ev.get("data_quality") or ev.get("status") or "—"
            actual = ev.get("actual")
            actual_s = "null" if actual is None else str(actual)
            lines.append(f"| {d} | {name} | {src} | {subtype} | {dqv} | {actual_s} |")
        if len(events) > 40:
            lines.append("")
            lines.append(f"> 另有 **{len(events) - 40}** 条仅在 JSON 中。")
        lines.append("")

    _emit_events("未来 7 天", "upcoming_7d")
    _emit_events("近 14 天（含今日）", "recent_14d")
    _emit_events("Fed / FOMC", "fed_calendar")
    _emit_events("经济数据（BLS/BEA）", "economic_calendar")
    _emit_events("国债拍卖", "treasury_calendar")
    _emit_events("市场结构（规则日期）", "market_structure_calendar")
    _emit_events("黄金衍生品", "gold_derivatives_calendar")
    return lines


def _news_quality_block(
    news_stats: dict[str, Any],
    news_articles: list[dict[str, Any]],
) -> list[str]:
    """Map actual NewsProvider stats keys + derive content_status counts."""
    raw = news_stats.get("raw_count", news_stats.get("raw_fetched"))
    dropped = news_stats.get("duplicates_dropped", news_stats.get("exact_dupes_dropped"))
    after = news_stats.get("after_deterministic_dedupe", len(news_articles))
    trunc_any = news_stats.get("possible_truncation_any", news_stats.get("possible_truncation"))

    feeds = news_stats.get("feeds") or []
    trunc_feeds = [
        f.get("feed") for f in feeds if f.get("possible_truncation")
    ]
    failed = [
        f"{f.get('feed')}: {f.get('error')}"
        for f in feeds
        if f.get("error")
    ]
    if not failed:
        failed = list(news_stats.get("failed_feeds") or [])

    title_only = news_stats.get("title_only")
    rss_only = news_stats.get("rss_summary_only")
    full_text = news_stats.get("full_text_count", news_stats.get("full_text_available"))
    if title_only is None or rss_only is None:
        c_title = sum(1 for a in news_articles if a.get("content_status") == "title_only")
        c_rss = sum(1 for a in news_articles if a.get("content_status") == "rss_summary_only")
        c_full = sum(
            1
            for a in news_articles
            if a.get("content_status") in ("full_text", "full_text_available")
        )
        title_only = c_title if title_only is None else title_only
        rss_only = c_rss if rss_only is None else rss_only
        full_text = c_full if full_text is None else full_text

    unknown_src = news_stats.get("unknown_source_name")
    if unknown_src is None:
        unknown_src = sum(1 for a in news_articles if not a.get("source_name"))

    redirect_n = news_stats.get("unresolved_redirect_count")
    if redirect_n is None:
        redirect_n = sum(1 for a in news_articles if a.get("url_is_google_news_redirect"))

    lines = [
        "## C. 新闻采集总览",
        "",
        f"- 时间窗口：**最近 {news_stats.get('lookback_hours', '—')} 小时**",
        f"- 原始拉取条数：**{raw if raw is not None else '—'}**",
        f"- 确定性去重后：**{after}**",
        f"- 精确重复丢弃：**{dropped if dropped is not None else '—'}**",
        f"- 仅标题（无真实摘要）：**{title_only if title_only is not None else '—'}**",
        f"- RSS 摘要：**{rss_only if rss_only is not None else '—'}**",
        f"- 全文可用：**{full_text if full_text is not None else 0}**",
        f"- 真实媒体名未确认：**{unknown_src}**",
        f"- Google News 跳转 URL：**{redirect_n}**",
        f"- 单源上限：{news_stats.get('per_feed_cap', '—')}",
        f"- **可能截断**：{'是 — ' + ', '.join(str(x) for x in trunc_feeds) if trunc_any else '否'}",
        f"- 失败 Feed：{', '.join(str(x) for x in failed) if failed else '无'}",
        "",
        "**以上数字仅描述采集覆盖，不是独立事件数，也不代表市场重要性。**",
        "",
    ]
    ft = full_text if full_text is not None else 0
    if ft == 0:
        lines.append(
            "> **本次只有 RSS 摘要，没有获取到全文。** "
            "请勿将 RSS 摘要当作全文正文使用。"
        )
        lines.append("")
    if feeds:
        lines.append("### 各 Feed 拉取计数")
        for f in feeds:
            flag = " ⚠trunc" if f.get("possible_truncation") else ""
            err = f" ERROR={f.get('error')}" if f.get("error") else ""
            lines.append(
                f"- {f.get('feed')}: fetched={f.get('fetched')}{flag}{err}"
            )
        lines.append("")

    if failed:
        lines.append("### 失败信息源")
        for f in failed:
            lines.append(f"- `{f}`")
        lines.append("")

    return lines


def build_daily_report(
    report_date: str,
    metrics: list[MetricPoint],
    run_id: str,
    indicators: dict[str, Any] | None = None,
    news_articles: list[dict[str, Any]] | None = None,
    news_stats: dict[str, Any] | None = None,
    quality_notes: list[str] | None = None,
    news_json_path: str | None = None,
    calendar_payload: dict[str, Any] | None = None,
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
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`  ·  schema **v0.9**",
        ">",
        "> **职责边界**：本报告仅含市场数据快照、官方日历与新闻采集清单。",
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

    lines += _render_calendar_section(calendar_payload, report_date)
    lines += _news_quality_block(news_stats, news_articles)

    news_link = news_json_path or f"data/news/{report_date}.json"
    lines += [
        "## D. 新闻清单",
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
            summary = a.get("summary")
            summary_s = (summary.replace("|", "/")[:100] if summary else "（无摘要）")
            url = a.get("original_url") or ""
            flag = "⚠跳转未解析" if a.get("url_is_google_news_redirect") else "原文"
            status = a.get("content_status") or "—"
            lines.append(
                f"| {pub} | {title_s} | {src} | {topic} | {summary_s} "
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
        "## E. 原始数据路径",
        "",
        f"- 市场指标：`data/daily/YYYY/MM/{report_date}.json`",
        f"- 官方日历：`data/calendar/{report_date}.json`",
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
