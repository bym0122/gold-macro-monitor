# gold-macro-monitor

黄金宏观监控｜GitHub Actions 低成本长期运行。

**目标**：每天自动汇总 **价格 + 宏观 + 仓位/财政 + 黄金/地缘新闻**，生成可供你撰写「黄金为何涨跌」分析的结构化报告。  
**不自动交易，不调用付费 LLM/行情 API。**

仓库：https://github.com/bym0122/gold-macro-monitor

## 每日产出

- `reports/YYYY-MM-DD.md`：结论候选、分层解释（宏观 / 事件 / 仓位）、高相关新闻表、数据快照
- `data/daily/.../YYYY-MM-DD.json`：机器可读 metrics + news + analysis

## 模块优先级

| 模块 | 每日重要性 | 状态 |
|------|------------|------|
| XAU/USD | 高 | ✅ goldprice.dev |
| 159934 | 高 | ✅ Yahoo |
| 实际利率等 FRED | 高 | ✅ |
| 美元/CNY | 高 | ✅ |
| **黄金/地缘新闻** | **高** | ✅ RSS 多源去重 + 相关度 1–5 |
| COT | 中高（周） | ✅ |
| 美国债务/利息 | 中高 | ✅ FiscalData |
| WGC ETF | 低（非硬依赖） | ⏭️ 无稳定自动源则跳过 |

## Secrets

| Name | 说明 |
|------|------|
| `FRED_API_KEY` | https://fred.stlouisfed.org/docs/api/api_key.html |

## 运行

- 每日 UTC 00:17（北京 08:17）`daily-gold.yml`
- 手动：Actions → Daily Gold Macro Monitor → Run workflow
- 本地：`PYTHONPATH=src python -m gold_monitor.cli daily`

## 新闻字段

`title, source, url, published_at, fetched_at, category, summary, entities, relevance_to_gold (1–5), sentiment`

报告只强调 **relevance ≥ 3**。相关度为关键词规则，**不是因果证明**。

## 声明

仅供研究，不构成投资建议。最终分析由你完成。
