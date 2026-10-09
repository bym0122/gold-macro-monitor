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
    return f"{p.value} {p.unit} ({p.status.value})"


def build_daily_report(
    report_date: str,
    metrics: list[MetricPoint],
    run_id: str,
) -> str:
    by_metric = {m.metric: m for m in metrics}
    now = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# 黄金宏观日报 {report_date}",
        "",
        f"> 生成时间 (UTC): {now}  ·  run_id: `{run_id}`",
        "",
        "## 1. 一句话结论",
        "",
        "（自动生成占位）今日核心数据已采集；黄金价格与 159934 来源尚未完成实测接入，"
        "请勿将缺失项解读为中性。原因未确认的部分直接标注。",
        "",
        "## 2. 价格与数据快照",
        "",
        "| 指标 | 数值 | 观测日 | 来源 | 状态 |",
        "|------|------|--------|------|------|",
    ]

    order = [
        "gold_xauusd",
        "etf_159934_close",
        "etf_159934_change_pct",
        "us_10y_real_yield",
        "us_10y_nominal_yield",
        "us_10y_breakeven_inflation",
    ]
    labels = {
        "gold_xauusd": "现货/期货黄金 (USD/oz)",
        "etf_159934_close": "159934 收盘价",
        "etf_159934_change_pct": "159934 涨跌幅",
        "us_10y_real_yield": "美债 10Y 实际收益率",
        "us_10y_nominal_yield": "美债 10Y 名义收益率",
        "us_10y_breakeven_inflation": "10Y 盈亏平衡通胀",
    }

    for key in order:
        p = by_metric.get(key)
        if not p:
            lines.append(f"| {labels.get(key, key)} | — | — | — | missing |")
            continue
        lines.append(
            f"| {labels.get(key, key)} | {_fmt_value(p)} | {p.observation_date or '—'} "
            f"| [{p.source}]({p.source_url}) | {p.status.value} |"
        )

    lines += [
        "",
        "## 3. 今天涨跌的候选解释",
        "",
        "（最多 3 条，需有支持证据与反证。当前为骨架，待黄金价格源接入后填充。）",
        "",
        "## 4. 长期逻辑是否变化",
        "",
        "本期无新的低频数据（WGC / COT / 财政）。不把上月资金流描述为今日发生。",
        "",
        "## 5. 短期风险与技术状态",
        "",
        "待黄金价格序列稳定后补充 5/20/60 日收益率与波动率。",
        "",
        "## 6. 对 159934 的含义",
        "",
        "数据源尚未验证，暂不给出跟踪误差或溢价判断。",
        "",
        "## 7. 下一步要盯的数据/事件",
        "",
        "1. 完成黄金价格免费源实测并写入 provider",
        "2. 完成 159934 免费源实测并写入 provider",
        "3. 配置 FRED_API_KEY 后验证 DFII10 / DGS10 / T10YIE",
        "",
        "## 8. 数据质量 / 失败清单",
        "",
    ]

    for p in metrics:
        flag = "✅" if p.status == DataStatus.OK else "⚠️"
        lines.append(
            f"- {flag} `{p.metric}`: status={p.status.value}, "
            f"obs={p.observation_date}, notes={p.notes or '—'}"
        )

    lines += [
        "",
        "## 9. 来源",
        "",
        "- FRED: https://fred.stlouisfed.org/",
        "- 本报告由 gold-macro-monitor 自动生成，仅供研究，不构成投资建议。",
        "",
    ]
    return "\n".join(lines)
