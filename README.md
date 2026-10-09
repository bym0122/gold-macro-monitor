# gold-macro-monitor

黄金宏观**数据采集**｜GitHub Actions 低成本长期运行。

## 职责边界（v0.5）

| 组件 | 负责 | 不负责 |
|------|------|--------|
| GitHub Actions / 本仓库脚本 | 拉行情与宏观数据、RSS 新闻采集、确定性去重、写 JSON/MD | 新闻事件聚类、利多利空、most_likely 因果 |
| 下游 ChatGPT（你） | 读 `data/news/*.json` + 日报做分析 | — |

**不自动交易。不调用付费 API / 付费模型。**

## 每日产出

| 路径 | 内容 |
|------|------|
| `data/daily/YYYY/MM/YYYY-MM-DD.json` | 市场指标 + 采集统计 |
| `data/news/YYYY-MM-DD.json` | **完整新闻**（ChatGPT 主输入） |
| `reports/YYYY-MM-DD.md` | 可读快照 + 新闻清单预览 |

## 市场数据（保留）

XAU/USD、159934、FRED 实际/名义/盈亏平衡、DXY、USD/CNY、COT、美国债务与利息支出。

## 新闻字段（news_v1）

`article_id, title, source_name, source_feed, original_url, url_is_google_news_redirect, published_at, fetched_at, summary, language, search_topic, keyword_tags, relevance_to_gold_rule_score`（规则分，非影响判断）, `headline_sentiment`（标题词，非方向结论）, `content_status, possible_duplicate`

- **无** `relevance >= 3` 硬过滤；低分文章同样保留。
- **无** 语义事件聚类。
- 确定性去重：规范化 URL / 标题。

## Secrets

`FRED_API_KEY` — https://fred.stlouisfed.org/docs/api/api_key.html

## 运行

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m gold_monitor.cli daily
pytest -q
```

Actions：每日 UTC 00:17；亦可 workflow_dispatch。

## 声明

仅供研究整理，不构成投资建议。
