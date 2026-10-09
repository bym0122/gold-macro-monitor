"""Generate Chinese daily analysis report (not just a data dump)."""

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
) -> str:
    by_metric = {m.metric: m for m in metrics}
    now = datetime.now(timezone.utc).isoformat()
    explanations = explanations or []
    indicators = indicators or {}
    news_items = news_items or []
    analysis = analysis or {}

    most_likely = analysis.get("most_likely") or "原因未确认"
    conf = analysis.get("confidence") or "低"

    gold = by_metric.get("gold_xauusd")
    etf = by_metric.get("etf_159934_close")
    etf_chg = by_metric.get("etf_159934_change_pct")

    lines = [
        f"# 黄金宏观日报 {report_date}",
        "",
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`  ·  版本 0.3",
        "",
        "## 结论（供人工写分析用）",
        "",
        f"**最可能原因（机器候选，非投资建议）**：{most_likely}",
        "",
        f"**置信度**：{conf}",
        "",
        "明确区分：**事实**（可追溯数据/原文链接） / **解释**（规则与并列） / **推测**（需你确认）。",
        "",
        "## 价格表现",
        "",
    ]
    if gold and gold.value is not None:
        lines.append(f"- **事实** XAU/USD：{gold.value:,.2f}（观测 {gold.observation_date}，{gold.status.value}）")
    else:
        lines.append("- **事实** XAU/USD：缺失")
    if etf and etf.value is not None:
        chg = f"，涨跌幅 {etf_chg.value:.2f}%" if etf_chg and etf_chg.value is not None else ""
        lines.append(f"- **事实** 159934 场内价：{etf.value} CNY{chg}（观测 {etf.observation_date}；非净值）")

    gchg = (indicators.get("gold_xauusd") or {}).get("chg_1d_pct")
    if gchg is not None:
        lines.append(f"- 相对昨日序列变动约 {gchg:.2f}%（需积累更多交易日才稳定）")
    else:
        lines.append("- 日变动：历史点不足，暂不计算")

    lines += ["", "## 分层解释", ""]
    for layer in analysis.get("layers") or []:
        lines.append(f"### {layer.get('title', '')}")
        lines.append(f"- **支持**：{layer.get('support')}")
        lines.append(f"- **反证/限制**：{layer.get('counter')}")
        lines.append(f"- **置信度**：{layer.get('confidence')}")
        lines.append(f"- **待核实**：{layer.get('todo')}")
        lines.append("")

    lines += ["## 高相关新闻（relevance ≥ 3）", ""]
    if not news_items:
        lines.append("暂无高相关新闻，或抓取失败。**不能**解释为今日无事件。")
    else:
        lines.append("| 相关 | 情绪 | 分类 | 标题 | 来源 | 时间 |")
        lines.append("|------|------|------|------|------|------|")
        for n in news_items[:15]:
            title = (n.get("title") or "").replace("|", "/")[:100]
            url = n.get("url") or ""
            lines.append(
                f"| {n.get('relevance_to_gold')} | {n.get('sentiment')} | {n.get('category')} "
                f"| [{title}]({url}) | {n.get('source')} | {(n.get('published_at') or '—')[:16]} |"
            )
        lines.append("")
        lines.append("> 摘要与实体为 RSS/关键词规则产物，请点开原文核对。")

    lines += ["", "## 数据快照", "",
              "| 指标 | 数值 | 观测日 | 来源 | 状态 |",
              "|------|------|--------|------|------|"]

    order = [
        ("gold_xauusd", "现货黄金 XAU/USD"),
        ("etf_159934_close", "159934 场内价"),
        ("etf_159934_change_pct", "159934 涨跌幅"),
        ("usd_cny", "美元兑人民币"),
        ("us_10y_real_yield", "美债 10Y 实际收益率"),
        ("us_10y_nominal_yield", "美债 10Y 名义收益率"),
        ("us_10y_breakeven_inflation", "10Y 盈亏平衡通胀"),
        ("cot_gold_net_noncommercial", "COT 净非商业（周）"),
        ("cot_gold_open_interest", "COT 未平仓（周）"),
        ("wgc_global_etf_holdings_t", "全球黄金 ETF 持仓（可选）"),
        ("us_total_public_debt", "美国公共债务总额"),
        ("us_interest_expense_fytd", "美国利息支出 FYTD"),
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

    lines += ["", "## 明日重点观察", ""]
    for i, w in enumerate(analysis.get("watchlist") or [], 1):
        lines.append(f"{i}. {w}")

    lines += ["", "## 数据质量", ""]
    for p in metrics:
        flag = "✅" if p.status == DataStatus.OK else ("⏳" if p.status == DataStatus.STALE else "⚠️")
        lines.append(
            f"- {flag} `{p.metric}`: {p.status.value}, obs={p.observation_date}, {p.notes or '—'}"
        )

    lines += [
        "",
        "## 来源与声明",
        "",
        "- 价格/宏观：goldprice.dev、Yahoo、FRED、FiscalData、CFTC(via futuresbench)",
        "- 新闻：Google News RSS、Fed 官方 RSS、BBC Mid-East、Al Jazeera 等（多源去重）",
        "- WGC：非每日硬依赖；无自动新数据时显示「暂无最新」，绝不把旧数据标成今天",
        "",
        "**本报告仅供研究整理，不构成投资建议。** 最终黄金分析结论由你在阅读本报告后撰写。",
        "",
    ]
    return "\n".join(lines)
