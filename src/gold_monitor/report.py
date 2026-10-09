"""Generate Chinese daily Markdown report."""

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
) -> str:
    by_metric = {m.metric: m for m in metrics}
    now = datetime.now(timezone.utc).isoformat()
    explanations = explanations or []
    indicators = indicators or {}

    # One-line conclusion from first explanation
    if explanations:
        one_liner = explanations[0].get("title", "原因未确认")
    else:
        one_liner = "原因未确认"

    lines = [
        f"# 黄金宏观日报 {report_date}",
        "",
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`",
        "",
        "## 1. 一句话结论",
        "",
        f"{one_liner}。以下区分事实 / 解释 / 推测；缺失数据不会被当作中性。",
        "",
        "## 2. 价格与数据快照",
        "",
        "| 指标 | 数值 | 观测日 | 来源 | 状态 |",
        "|------|------|--------|------|------|",
    ]

    order = [
        ("gold_xauusd", "现货黄金 XAU/USD"),
        ("etf_159934_close", "159934 场内价"),
        ("etf_159934_change_pct", "159934 涨跌幅"),
        ("usd_cny", "美元兑人民币"),
        ("us_10y_real_yield", "美债 10Y 实际收益率"),
        ("us_10y_nominal_yield", "美债 10Y 名义收益率"),
        ("us_10y_breakeven_inflation", "10Y 盈亏平衡通胀"),
        ("cot_gold_net_noncommercial", "COT 净非商业（周）"),
        ("cot_gold_net_commercial", "COT 净商业（周）"),
        ("cot_gold_open_interest", "COT 未平仓（周）"),
        ("wgc_global_etf_holdings_t", "全球黄金 ETF 持仓（吨）"),
        ("wgc_global_etf_flow_usd_mn", "全球黄金 ETF 流量（百万美元）"),
        ("us_total_public_debt", "美国公共债务总额"),
        ("us_interest_expense_fytd", "美国利息支出 FYTD"),
    ]

    for key, label in order:
        p = by_metric.get(key)
        if not p:
            lines.append(f"| {label} | — | — | — | missing |")
            continue
        lines.append(
            f"| {label} | {_fmt_value(p)} | {p.observation_date or '—'} "
            f"| [{p.source}]({p.source_url}) | {p.status.value} |"
        )

    lines += ["", "### 简易变动（需历史数据）", ""]
    for k, snap in indicators.items():
        lines.append(
            f"- `{k}`: hist={snap.get('history_points')}, "
            f"1d%={snap.get('chg_1d_pct')}, 5d%={snap.get('chg_5d_pct')}"
        )

    lines += ["", "## 3. 今天涨跌的候选解释", ""]
    for i, ex in enumerate(explanations, 1):
        lines.append(f"### 候选 {i}: {ex.get('title')}")
        lines.append(f"- **支持证据**: {ex.get('support')}")
        lines.append(f"- **反证**: {ex.get('counter')}")
        lines.append(f"- **置信度**: {ex.get('confidence')}")
        lines.append(f"- **待核实**: {ex.get('todo')}")
        lines.append("")

    lines += [
        "## 4. 长期逻辑是否变化",
        "",
        "财政/债务、官方购金、ETF 资金流为低频数据。",
        "若本期无新数据，写明「本期无新数据」，不把上月流量说成今日发生。",
        "",
    ]
    debt = by_metric.get("us_total_public_debt")
    if debt and debt.status == DataStatus.OK:
        lines.append(
            f"- **事实**: 美国公共债务总额观测日 {debt.observation_date}: {_fmt_value(debt)}"
        )
    else:
        lines.append("- 债务数据缺失或无效。")
    wgc_h = by_metric.get("wgc_global_etf_holdings_t")
    if wgc_h and wgc_h.status == DataStatus.OK:
        lines.append(f"- **事实**: WGC 全球 ETF 持仓: {_fmt_value(wgc_h)}（{wgc_h.observation_date}）")
    else:
        lines.append(
            "- WGC ETF：无自动源；可手工写入 `data/manual/wgc_etf_flows.csv`。"
        )

    lines += [
        "",
        "## 5. 短期风险与技术状态",
        "",
        "COT 为周度仓位背景，不可当作当日信号。波动率/均线需积累更多日频序列后补充。",
        "",
        "## 6. 对 159934 的含义",
        "",
    ]
    etf = by_metric.get("etf_159934_close")
    gold = by_metric.get("gold_xauusd")
    fx = by_metric.get("usd_cny")
    if etf and etf.status == DataStatus.OK:
        lines.append(
            f"- **事实**: 159934 场内价 {etf.value} CNY（观测 {etf.observation_date}），"
            "这是交易所价格，不是基金净值；溢价/折价需同日净值才可算。"
        )
    if gold and gold.status in (DataStatus.OK, DataStatus.STALE) and fx and fx.status == DataStatus.OK:
        lines.append(
            f"- 美元金价与 USD/CNY 同时可得时，人民币金价方向可能与美元金价不完全一致；"
            "此处仅并列展示，不做硬性换算结论。"
        )
    lines.append("- 不自动给出买卖建议。")

    lines += [
        "",
        "## 7. 下一步要盯的数据/事件",
        "",
        "1. FRED 实际利率 / 盈亏平衡下一次更新",
        "2. 下周 COT（周二持仓、周五前后发布）",
        "3. WGC 月度 ETF 流量（手工或官网）",
        "4. 美国财政月报 / 债务上限与拍卖相关新闻",
        "5. 与黄金相关的地缘与央行购金报道（区分事实与推测）",
        "",
        "## 8. 数据质量 / 失败清单",
        "",
    ]
    for p in metrics:
        flag = "✅" if p.status == DataStatus.OK else ("⏳" if p.status == DataStatus.STALE else "⚠️")
        lines.append(
            f"- {flag} `{p.metric}`: status={p.status.value}, "
            f"obs={p.observation_date}, notes={p.notes or '—'}"
        )

    lines += [
        "",
        "## 9. 来源",
        "",
        "- FRED: https://fred.stlouisfed.org/",
        "- goldprice.dev XAU-USD-SPOT",
        "- Yahoo Finance 159934.SZ / CNY=X",
        "- CFTC COT via futuresbench.com",
        "- U.S. Treasury FiscalData",
        "- WGC Goldhub（手工 CSV 可选）",
        "",
        "本报告由 gold-macro-monitor 自动生成，仅供研究，**不构成投资建议**。",
        "",
    ]
    return "\n".join(lines)
