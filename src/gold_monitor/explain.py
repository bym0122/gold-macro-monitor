"""Layered gold analysis: events + market cross-check. Not trading signals."""

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
    return p.status.value if p else "missing"


def _market_verify(
    prior: str,
    gold_chg: Optional[float],
    real_chg: Optional[float],
    dxy_chg: Optional[float],
) -> tuple[str, str]:
    """Cross-check event prior against price/rates/DXY. Returns (impact, evidence)."""
    bits = []
    if gold_chg is not None:
        bits.append(f"金价日变动≈{gold_chg:+.2f}%")
    if real_chg is not None:
        bits.append(f"实际利率日变动≈{real_chg:+.2f}%")
    if dxy_chg is not None:
        bits.append(f"DXY日变动≈{dxy_chg:+.2f}%")
    evidence = "；".join(bits) if bits else "市场日变动序列不足，仅保留事件观察"

    if gold_chg is None:
        return "待市场验证", evidence

    # Confirmed paths
    if prior == "bearish_prior" and gold_chg < 0:
        if (real_chg is not None and real_chg > 0) or (dxy_chg is not None and dxy_chg > 0):
            return "确认偏空（事件先验 + 金价↓ + 利率/美元至少一项↑）", evidence
        return "方向一致偏空（金价↓，利率/美元验证不足）", evidence
    if prior == "bullish_prior" and gold_chg > 0:
        if (real_chg is not None and real_chg < 0) or (dxy_chg is not None and dxy_chg < 0):
            return "确认偏多（事件先验 + 金价↑ + 利率/美元至少一项↓）", evidence
        return "方向一致偏多（金价↑，利率/美元未同步支持——或有避险主导）", evidence
    if prior == "bearish_prior" and gold_chg > 0:
        return "事件偏空但金价上涨（需其他驱动解释）", evidence
    if prior == "bullish_prior" and gold_chg < 0:
        return "事件偏多但金价下跌（需其他驱动解释）", evidence
    return "中性/混杂", evidence


def candidate_explanations(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
    news_items: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    layers = build_layered_analysis(metrics, indicator_snap, news_items or [], events or [])
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
                "support": "数据或事件不足以形成可检验解释",
                "counter": "—",
                "confidence": "低",
                "todo": "等待更多日频序列与独立事件",
            }
        )
    return cands


def build_layered_analysis(
    metrics: dict[str, MetricPoint],
    indicator_snap: dict[str, Any],
    news_items: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = events or []
    gold = _val(metrics, "gold_xauusd")
    real = _val(metrics, "us_10y_real_yield")
    dxy = _val(metrics, "dxy")
    dxy_chg_metric = _val(metrics, "dxy_change_pct")
    cot = _val(metrics, "cot_gold_net_noncommercial")
    gold_chg = (indicator_snap.get("gold_xauusd") or {}).get("chg_1d_pct")
    real_chg = (indicator_snap.get("us_10y_real_yield") or {}).get("chg_1d_pct")
    dxy_hist_chg = (indicator_snap.get("dxy") or {}).get("chg_1d_pct")
    dxy_chg = dxy_hist_chg if dxy_hist_chg is not None else dxy_chg_metric

    layers: list[dict[str, Any]] = []

    # Macro layer with DXY
    macro_bias = "中性"
    support = []
    if real is not None:
        support.append(f"10Y实际收益率 {real:.3f}%")
    if dxy is not None:
        support.append(f"DXY {dxy:.3f}" + (f"（日变动 {dxy_chg:+.2f}%）" if dxy_chg is not None else ""))
    if real_chg is not None and dxy_chg is not None:
        if real_chg < 0 and dxy_chg < 0:
            macro_bias = "偏利多（利率↓且美元↓）"
        elif real_chg > 0 and dxy_chg > 0:
            macro_bias = "偏利空（利率↑且美元↑）"
        elif real_chg < 0 and dxy_chg > 0:
            macro_bias = "混杂（利率↓但美元↑）"
        elif real_chg > 0 and dxy_chg < 0:
            macro_bias = "混杂（利率↑但美元↓）"
    elif real_chg is not None:
        macro_bias = "偏利多" if real_chg < 0 else ("偏利空" if real_chg > 0 else "中性")
        support.append(f"实际利率日变动≈{real_chg:+.2f}%")
    elif dxy_chg is not None:
        macro_bias = "偏利多" if dxy_chg < 0 else ("偏利空" if dxy_chg > 0 else "中性")
    if not support:
        support.append("宏观核心序列部分缺失")

    layers.append(
        {
            "layer": "macro",
            "title": f"第一层·宏观：{macro_bias}",
            "support": "；".join(support),
            "counter": "USD/CNY 服务 159934，不能代替 DXY 判断美元对金价的全球通道",
            "confidence": "中" if (real is not None and dxy is not None) else "低",
            "todo": "与名义收益率、破均衡通胀交叉看",
        }
    )

    # Event layer — independent events, not article count
    event_rows = []
    for ev in events[:8]:
        impact, evid = _market_verify(
            ev.get("prior_bias") or "neutral_prior", gold_chg, real_chg, dxy_chg
        )
        event_rows.append(
            {
                "event_id": ev.get("event_id"),
                "label": ev.get("label"),
                "sources": ev.get("source_count"),
                "articles": ev.get("article_count"),
                "prior_bias": ev.get("prior_bias"),
                "market_impact": impact,
                "market_evidence": evid,
                "first_published_at": ev.get("first_published_at"),
                "latest_published_at": ev.get("latest_published_at"),
                "sample_titles": ev.get("sample_titles") or [],
            }
        )

    if event_rows:
        summary = "；".join(
            f"{e['label']}（源{e['sources']}家→{e['market_impact'][:12]}）" for e in event_rows[:4]
        )
        layers.append(
            {
                "layer": "events",
                "title": f"第二层·独立事件：{len(event_rows)} 个（非文章条数）",
                "support": summary,
                "counter": "标题情绪(headline_sentiment)不参与因果；同事件多源只计一次",
                "confidence": "中" if len(event_rows) >= 2 else "低",
                "todo": "点开各事件 sample 原文核对事实时间戳",
            }
        )
    else:
        layers.append(
            {
                "layer": "events",
                "title": "第二层·独立事件：暂无",
                "support": "未形成可聚类的高相关事件（或抓取失败）",
                "counter": "不能解释为今日无事件",
                "confidence": "低",
                "todo": "检查 RSS/关键词",
            }
        )

    # Positioning
    if cot is not None:
        layers.append(
            {
                "layer": "positioning",
                "title": "第三层·资金/仓位：周度背景",
                "support": f"COT净非商业约 {cot:,.0f} 手（周度滞后，不能单独解释今日）",
                "counter": "WGC 非每日硬依赖",
                "confidence": "低",
                "todo": "与上周 COT 对比",
            }
        )
    else:
        layers.append(
            {
                "layer": "positioning",
                "title": "第三层·资金/仓位：不足",
                "support": "COT 不可用",
                "counter": "—",
                "confidence": "低",
                "todo": "检查 COT 源",
            }
        )

    # Most likely narrative
    most_likely = "原因未确认"
    conf = "低"
    geo_events = [e for e in event_rows if e.get("event_id", "").startswith("E_") and e["event_id"] in
                  ("E_IRAN_HORMUZ", "E_ISRAEL_GAZA", "E_US_IRAN", "E_UKRAINE", "E_TAIWAN")]
    fed_hawk = next((e for e in event_rows if e.get("event_id") == "E_FED_HAWK"), None)

    if gold_chg is not None and real_chg is not None and dxy_chg is not None:
        if gold_chg > 0 and real_chg < 0 and dxy_chg < 0:
            most_likely = "金价上涨与「实际利率↓ + DXY↓」同向，宏观顺风是主候选；地缘事件作增强项"
            conf = "中"
        elif gold_chg > 0 and (real_chg > 0 or dxy_chg > 0) and geo_events:
            most_likely = "利率/美元至少一项不支持金价，但出现地缘独立事件且金价上涨——避险/事件驱动是主候选"
            conf = "中"
        elif gold_chg < 0 and (real_chg > 0 or dxy_chg > 0) and fed_hawk:
            most_likely = "金价下跌与 Fed 偏鹰事件 + 利率/美元压力同向，宏观逆风是主候选"
            conf = "中"
        elif gold_chg < 0 and real_chg > 0 and dxy_chg > 0:
            most_likely = "金价↓且实际利率↑、DXY↑，传统宏观逆风解释较强"
            conf = "中"
        else:
            most_likely = "价格与利率/DXY/事件组合未形成单一主因，保持原因未确认"
            conf = "低"
    elif event_rows and gold is not None:
        most_likely = f"已识别 {len(event_rows)} 个独立事件，但日变动历史不足，因果强度有限"
        conf = "低"

    return {
        "most_likely": most_likely,
        "confidence": conf,
        "layers": layers,
        "event_analysis": event_rows,
        "news_stats": {
            "article_count": len(news_items),
            "independent_event_count": len(event_rows),
            "geo_event_count": len(geo_events),
        },
        "watchlist": [
            "10Y 实际收益率（DFII10）",
            "DXY 美元指数",
            "伊朗/霍尔木兹/美伊 独立事件是否升级",
            "Fed 官员讲话与通胀数据",
            "COT 周度（勿当日化）",
        ],
    }
