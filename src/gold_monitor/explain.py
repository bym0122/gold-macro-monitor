"""Layered gold move analysis: macro + events + positioning — not trading signals."""

from __future__ import annotations

from typing import Any, Optional

from .providers.base import MetricPoint, DataStatus


def _val(metrics: dict[str, MetricPoint], key: str) -> Optional[float]:
    p = metrics.get(key)
    if p and p.status in (DataStatus.OK, DataStatus.STALE) and p.value is not None:
        return p.value
    return None


def _status_label(metrics: dict[str, MetricPoint], key: str) -> str:
    p = metrics.get(key)
    if not p:
        return "missing"
    return p.status.value


def candidate_explanations(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
    news_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Legacy short candidates (kept for JSON compatibility)."""
    layers = build_layered_analysis(metrics, indicator_snap, news_items or [])
    cands = []
    for layer in layers.get("layers", [])[:3]:
        cands.append(
            {
                "title": layer.get("title", ""),
                "support": layer.get("support", ""),
                "counter": layer.get("counter", ""),
                "confidence": layer.get("confidence", "低"),
                "todo": layer.get("todo", ""),
            }
        )
    if not cands:
        cands.append(
            {
                "title": "原因未确认",
                "support": "数据或新闻不足以形成可检验解释",
                "counter": "—",
                "confidence": "低",
                "todo": "等待更多日频序列与高相关新闻",
            }
        )
    return cands


def build_layered_analysis(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
    news_items: list[dict[str, Any]],
) -> dict[str, Any]:
    gold = _val(metrics, "gold_xauusd")
    real = _val(metrics, "us_10y_real_yield")
    nominal = _val(metrics, "us_10y_nominal_yield")
    fx = _val(metrics, "usd_cny")
    cot = _val(metrics, "cot_gold_net_noncommercial")
    gold_chg = (indicator_snap.get("gold_xauusd") or {}).get("chg_1d_pct")
    real_chg = (indicator_snap.get("us_10y_real_yield") or {}).get("chg_1d_pct")

    high_news = [n for n in news_items if int(n.get("relevance_to_gold") or 0) >= 3]
    geo_news = [n for n in high_news if n.get("category") in ("geopolitics", "gold_geo")]
    macro_news = [n for n in high_news if n.get("category") in ("us_macro", "gold")]
    bull_n = sum(1 for n in high_news if n.get("sentiment") == "bullish_gold")
    bear_n = sum(1 for n in high_news if n.get("sentiment") == "bearish_gold")

    layers: list[dict[str, Any]] = []

    # Layer 1: macro drivers
    macro_bias = "中性"
    macro_support = []
    macro_counter = []
    if real is not None:
        macro_support.append(f"10Y 实际收益率最新 {real:.3f}%（状态 {_status_label(metrics, 'us_10y_real_yield')}）")
    if real_chg is not None:
        if real_chg < 0:
            macro_bias = "偏利多"
            macro_support.append(f"实际利率近况变动约 {real_chg:.2f}%（下降通常对黄金偏支持）")
        elif real_chg > 0:
            macro_bias = "偏利空"
            macro_support.append(f"实际利率近况变动约 {real_chg:.2f}%（上升通常对黄金偏压力）")
        else:
            macro_support.append("实际利率日变动接近持平")
    else:
        macro_counter.append("尚无足够历史序列计算实际利率日变动")
    if fx is not None:
        macro_support.append(f"USD/CNY≈{fx:.3f}")
    if not macro_support:
        macro_support.append("宏观核心序列部分缺失")
    layers.append(
        {
            "layer": "macro",
            "title": f"第一层·宏观：{macro_bias}",
            "support": "；".join(macro_support),
            "counter": "；".join(macro_counter) if macro_counter else "美元/广义美元指数若与金价同向，需降级单一利率解释",
            "confidence": "中" if real is not None else "低",
            "todo": "核对 DXY 与名义收益率是否同向",
        }
    )

    # Layer 2: event / news
    if high_news:
        tops = high_news[:5]
        titles = "；".join(f"[{n.get('relevance_to_gold')}] {n.get('title', '')[:80]}" for n in tops)
        if geo_news and bull_n >= bear_n:
            event_bias = "偏利多（避险/地缘叙事较多）"
        elif geo_news and bear_n > bull_n:
            event_bias = "混杂/偏空叙事"
        elif bull_n > bear_n:
            event_bias = "偏利多叙事"
        elif bear_n > bull_n:
            event_bias = "偏利空叙事"
        else:
            event_bias = "中性/混杂"
        layers.append(
            {
                "layer": "events",
                "title": f"第二层·事件：{event_bias}",
                "support": f"高相关新闻 {len(high_news)} 条；样本：{titles}",
                "counter": "新闻情绪为关键词规则，不是因果证明；同源转载可能放大权重",
                "confidence": "中" if len(high_news) >= 3 else "低",
                "todo": "点开原文核对时间戳与事实，勿把标题当结论",
            }
        )
    else:
        layers.append(
            {
                "layer": "events",
                "title": "第二层·事件：暂无高相关新闻",
                "support": "过去约 36 小时内未筛到 relevance≥3 的条目（或抓取失败）",
                "counter": "RSS 覆盖有限，不能解释为‘无事件’",
                "confidence": "低",
                "todo": "检查新闻源可用性或放宽关键词",
            }
        )

    # Layer 3: positioning
    if cot is not None:
        layers.append(
            {
                "layer": "positioning",
                "title": "第三层·资金/仓位：周度背景",
                "support": f"COT 净非商业约 {cot:,.0f} 手（观测日见数据表；周度滞后，不能单独解释今日波动）",
                "counter": "ETF/WGC 若无当日更新，不得写成今日流入",
                "confidence": "低",
                "todo": "与上周 COT 对比拥挤度",
            }
        )
    else:
        layers.append(
            {
                "layer": "positioning",
                "title": "第三层·资金/仓位：数据不足",
                "support": "COT 或其他仓位序列不可用",
                "counter": "—",
                "confidence": "低",
                "todo": "检查 COT CSV 源",
            }
        )

    # Overall most-likely (cautious)
    most_likely = "原因未确认"
    conf = "低"
    if gold_chg is not None and real_chg is not None and high_news:
        if gold_chg > 0 and real_chg < 0 and geo_news:
            most_likely = "金价上涨更可能由「实际利率回落 + 地缘风险叙事」共同推动；需用美元与原文事实交叉验证"
            conf = "中"
        elif gold_chg > 0 and real_chg > 0 and geo_news:
            most_likely = "金价在实际利率上升背景下仍涨，优先检查地缘/避险与仓位因素，而非传统利率通道"
            conf = "中"
        elif gold_chg < 0 and real_chg > 0:
            most_likely = "金价下跌与实际利率上升同向，宏观逆风是候选主因；仍需排除单纯获利了结"
            conf = "中"
        else:
            most_likely = "价格与利率/新闻组合未形成清晰单一主因，保持原因未确认"
            conf = "低"
    elif high_news and gold is not None:
        most_likely = "有高相关新闻但历史价格变动不足，今日解释以事件观察为主、因果强度有限"
        conf = "低"

    return {
        "most_likely": most_likely,
        "confidence": conf,
        "layers": layers,
        "news_stats": {
            "high_relevance_count": len(high_news),
            "geo_count": len(geo_news),
            "macro_count": len(macro_news),
            "bullish_tagged": bull_n,
            "bearish_tagged": bear_n,
        },
        "watchlist": [
            "美债实际利率（DFII10）下一次更新",
            "美元（USD/CNY 与未来可加的 DXY）",
            "中东/伊朗相关可靠来源进展",
            "Fed 官员讲话与数据（CPI/PCE/就业）",
            "COT 周度更新（勿当日化）",
        ],
    }
