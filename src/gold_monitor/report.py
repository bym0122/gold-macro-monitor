"""Chinese daily analysis report for human gold write-ups."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .providers.base import MetricPoint, DataStatus


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


def build_daily_report(
    report_date: str,
    metrics: list[MetricPoint],
    run_id: str,
    explanations: list[dict[str, Any]] | None = None,
    indicators: dict[str, Any] | None = None,
    news_items: list[dict[str, Any]] | None = None,
    analysis: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> str:
    by_metric = {m.metric: m for m in metrics}
    now = datetime.now(timezone.utc).isoformat()
    indicators = indicators or {}
    news_items = news_items or []
    analysis = analysis or {}
    events = events or []

    most_likely = analysis.get("most_likely") or "原因未确认"
    conf = analysis.get("confidence") or "低"
    event_analysis = analysis.get("event_analysis") or []

    gold = by_metric.get("gold_xauusd")
    etf = by_metric.get("etf_159934_close")
    etf_chg = by_metric.get("etf_159934_change_pct")
    dxy = by_metric.get("dxy")
    dxy_chg = by_metric.get("dxy_change_pct")

    lines = [
        f"# 黄金宏观日报 {report_date}",
        "",
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`  ·  v0.4",
        "",
        "## 结论（供你写分析）",
        "",
        f"**最可能原因（机器候选）**：{most_likely}",
        "",
        f"**置信度**：{conf}",
        "",
        f"独立事件数：**{analysis.get('news_stats', {}).get('independent_event_count', len(event_analysis))}**"
        f"（文章数 {len(news_items)}，勿把文章数当事件数）",
        "",
        "## 价格与美元",
        "",
    ]
    if gold and gold.value is not None:
        lines.append(f"- **事实** XAU/USD：{gold.value:,.2f}（{gold.observation_date}）")
    if etf and etf.value is not None:
        chg = f"，{etf_chg.value:+.2f}%" if etf_chg and etf_chg.value is not None else ""
        lines.append(f"- **事实** 159934：{etf.value} CNY{chg}（场内价，非净值）")
    if dxy and dxy.value is not None:
        dc = f"，日变动 {dxy_chg.value:+.3f}%" if dxy_chg and dxy_chg.value is not None else ""
        lines.append(f"- **事实** DXY：{dxy.value:.3f}{dc}（{dxy.observation_date}）")
    else:
        lines.append("- DXY：缺失")

    gchg = (indicators.get("gold_xauusd") or {}).get("chg_1d_pct")
    lines.append(
        f"- 金价序列日变动：{gchg:+.2f}%" if gchg is not None else "- 金价日变动：历史不足"
    )

    lines += ["", "## 今日独立事件（聚类后）", ""]
    if not event_analysis:
        lines.append("暂无独立事件聚类结果。")
    else:
        for i, e in enumerate(event_analysis, 1):
            lines.append(f"### {i}. {e.get('label')} (`{e.get('event_id')}`)")
            lines.append(
                f"- 来源数：**{e.get('sources')}** 家 · 文章数：{e.get('articles')} "
                f"· 首发：{(e.get('first_published_at') or '—')[:16]} "
                f"· 最新：{(e.get('latest_published_at') or '—')[:16]}"
            )
            lines.append(f"- 事件先验（仅分类用）：{e.get('prior_bias')}")
            lines.append(f"- **市场交叉验证**：{e.get('market_impact')}")
            lines.append(f"- 验证依据：{e.get('market_evidence')}")
            samples = e.get("sample_titles") or []
            if samples:
                lines.append("- 样本标题：")
                for t in samples[:3]:
                    lines.append(f"  - {t}")
            lines.append("")

    lines += ["## 分层解释", ""]
    for layer in analysis.get("layers") or []:
        lines.append(f"### {layer.get('title', '')}")
        lines.append(f"- **支持**：{layer.get('support')}")
        lines.append(f"- **反证/限制**：{layer.get('counter')}")
        lines.append(f"- **置信度**：{layer.get('confidence')}")
        lines.append("")

    lines += ["## 数据快照", "",
              "| 指标 | 数值 | 观测日 | 来源 | 状态 |",
              "|------|------|--------|------|------|"]
    order = [
        ("gold_xauusd", "现货黄金 XAU/USD"),
        ("dxy", "美元指数 DXY"),
        ("dxy_change_pct", "DXY 日变动"),
        ("etf_159934_close", "159934 场内价"),
        ("etf_159934_change_pct", "159934 涨跌幅"),
        ("usd_cny", "美元兑人民币"),
        ("us_10y_real_yield", "美债 10Y 实际收益率"),
        ("us_10y_nominal_yield", "美债 10Y 名义收益率"),
        ("us_10y_breakeven_inflation", "10Y 盈亏平衡通胀"),
        ("cot_gold_net_noncommercial", "COT 净非商业（周）"),
        ("us_total_public_debt", "美国公共债务总额"),
        ("us_interest_expense_fytd", "美国利息支出 FYTD"),
        ("wgc_global_etf_holdings_t", "WGC ETF 持仓（可选）"),
    ]
    for key, label in order:
        p = by_metric.get(key)
        if not p:
            lines.append(f"| {label} | — | — | — | missing |")
            continue
        if key.startswith("wgc_") and p.status != DataStatus.OK:
            lines.append(f"| {label} | 暂无最新自动数据 | — | WGC | skipped |")
            continue
        lines.append(
            f"| {label} | {_fmt_value(p)} | {p.observation_date or '—'} "
            f"| [{p.source}]({p.source_url}) | {p.status.value} |"
        )

    lines += ["", "## 文章明细（次要，已按事件聚类）", ""]
    if news_items:
        lines.append(f"共 {len(news_items)} 篇 relevance≥3；下表仅供溯源，**请看上方独立事件**。")
        lines.append("")
        lines.append("| 事件 | 相关 | 标题情绪* | 标题 | 来源 |")
        lines.append("|------|------|-----------|------|------|")
        for n in news_items[:20]:
            title = (n.get("title") or "").replace("|", "/")[:90]
            hs = n.get("headline_sentiment") or n.get("sentiment") or "—"
            lines.append(
                f"| {n.get('event_id', '—')} | {n.get('relevance_to_gold')} | {hs} "
                f"| [{title}]({n.get('url')}) | {n.get('source')} |"
            )
        lines.append("")
        lines.append("> \*headline_sentiment 仅为标题关键词，**不参与**最终利多/利空判定。")
    else:
        lines.append("无文章。")

    lines += ["", "## 明日观察", ""]
    for i, w in enumerate(analysis.get("watchlist") or [], 1):
        lines.append(f"{i}. {w}")

    lines += [
        "",
        "## 声明",
        "",
        "事实可追溯；解释为规则+交叉验证；最终分析由你撰写。不构成投资建议。",
        "",
    ]
    return "\n".join(lines)
