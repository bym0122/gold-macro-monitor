"""Rule-based candidate explanations — not trading signals."""

from __future__ import annotations

from typing import Any, Optional

from .providers.base import MetricPoint, DataStatus


def _val(metrics: dict[str, MetricPoint], key: str) -> Optional[float]:
    p = metrics.get(key)
    if p and p.status in (DataStatus.OK, DataStatus.STALE) and p.value is not None:
        return p.value
    return None


def candidate_explanations(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Up to 3 candidates with evidence / counter / confidence."""
    gold = _val(metrics, "gold_xauusd")
    real = _val(metrics, "us_10y_real_yield")
    gold_chg = (indicator_snap.get("gold_xauusd") or {}).get("chg_1d_pct")
    real_chg = (indicator_snap.get("us_10y_real_yield") or {}).get("chg_1d_pct")

    cands: list[dict[str, Any]] = []

    if gold is None:
        cands.append(
            {
                "title": "黄金价格数据缺失",
                "support": "今日未能取得有效 XAU/USD 报价",
                "counter": "—",
                "confidence": "高",
                "todo": "检查 goldprice.dev 可用性",
            }
        )
        return cands[:3]

    # Directional rules only when we have changes
    if gold_chg is not None and real_chg is not None:
        if gold_chg > 0 and real_chg < 0:
            cands.append(
                {
                    "title": "短期宏观顺风候选（金价↑ + 实际利率↓）",
                    "support": f"金价日变动约 {gold_chg:.2f}%，实际利率日变动约 {real_chg:.2f}%",
                    "counter": "可能同期噪声；需核对美元与新闻",
                    "confidence": "中",
                    "todo": "核对 DXY/广义美元与当日新闻",
                }
            )
        elif gold_chg > 0 and real_chg > 0:
            cands.append(
                {
                    "title": "传统逆风下仍上涨",
                    "support": f"金价↑({gold_chg:.2f}%) 且实际利率↑({real_chg:.2f}%)",
                    "counter": "或有央行/ETF/地缘/仓位挤压等替代解释，证据不足时不得断言",
                    "confidence": "低",
                    "todo": "查看 COT、ETF 流量与地缘新闻",
                }
            )
        elif gold_chg < 0 and real_chg > 0:
            cands.append(
                {
                    "title": "短期宏观逆风候选（金价↓ + 实际利率↑）",
                    "support": f"金价日变动约 {gold_chg:.2f}%，实际利率日变动约 {real_chg:.2f}%",
                    "counter": "也可能是获利了结或流动性需求",
                    "confidence": "中",
                    "todo": "结合成交量与 ETF 流量",
                }
            )

    if not cands:
        cands.append(
            {
                "title": "原因未确认",
                "support": "历史序列不足或涨跌与利率组合不匹配简单规则",
                "counter": "—",
                "confidence": "低",
                "todo": "积累更多交易日数据后再比较",
            }
        )

    # COT context (weekly, not same-day)
    cot = _val(metrics, "cot_gold_net_noncommercial")
    if cot is not None:
        cands.append(
            {
                "title": "COT 投机净多头背景（周度，非当日）",
                "support": f"最新 COT 净非商业持仓约 {cot:,.0f} 手",
                "counter": "COT 有发布滞后，不能解释今日分钟级波动",
                "confidence": "低",
                "todo": "与前值比较拥挤度",
            }
        )

    return cands[:3]
