# gold-macro-monitor

黄金宏观监控｜GitHub Actions 低成本长期运行项目。

**只采集、归档、计算和生成报告，不自动交易。**  
不依赖付费 AI API、付费行情 API 或 Copilot。数据源接口在实现时必须实测，不得把未经验证的接口写成“稳定可用”。

仓库：`bym0122/gold-macro-monitor`（Private）

设计方案来源：Notion「黄金宏观监控｜GitHub Actions 实施设计方案（2026-10-09）」

## 核心原则

- 长期财政与货币信用逻辑、短期实际利率/美元交易驱动、资金流/仓位、价格趋势必须**分层分析**。
- 每个数字必须可追溯到来源、观测日期、抓取时间和状态。
- 缺失 / 过期 / 无效数据不得自动填 0 或伪装成中性。
- 报告明确区分「事实」「解释」「推测」。

## Phase 1 MVP 范围

1. FRED 三个核心利率序列：`DFII10`、`DGS10`、`T10YIE`
2. 一个经过实测的黄金价格来源
3. 一个经过实测的 159934 来源
4. 数据规范化、日期/过期检查、历史 JSON、每日 Markdown 报告
5. Actions Summary + 手动触发 + 基础测试

先稳定跑 10 个运行日，再扩展 Phase 2/3。

## 快速开始

### 1. Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：

| Name | 说明 |
|------|------|
| `FRED_API_KEY` | 免费申请：https://fred.stlouisfed.org/docs/api/api_key.html |

### 2. 本地运行（可选）

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FRED_API_KEY=your_key
python -m gold_monitor.cli daily
```

### 3. GitHub Actions

- 每天北京时间 08:17（UTC 00:17）自动运行
- 支持 `workflow_dispatch` 手动触发
- 报告写入 `reports/YYYY-MM-DD.md` 与对应 JSON

## 目录结构

```
gold-macro-monitor/
├── .github/workflows/
│   ├── daily-gold.yml
│   └── ci.yml
├── config/
│   ├── sources.yaml
│   └── thresholds.yaml
├── src/gold_monitor/
│   ├── providers/
│   ├── normalize.py
│   ├── validate.py
│   ├── indicators.py
│   ├── report.py
│   ├── storage.py
│   └── cli.py
├── data/
│   ├── daily/
│   └── state/
├── reports/
├── tests/
├── requirements.txt
└── README.md
```

## 数据状态约定

每条数据必须包含：

```json
{
  "metric": "us_10y_real_yield",
  "value": 1.72,
  "unit": "percent",
  "source": "FRED",
  "source_url": "https://fred.stlouisfed.org/series/DFII10",
  "observation_date": "YYYY-MM-DD",
  "fetched_at_utc": "ISO-8601",
  "status": "ok|stale|missing|invalid|estimated",
  "notes": ""
}
```

- `ok`：日期和字段通过检查
- `stale`：数据存在但超出预期更新间隔
- `missing`：没有拿到数据
- `invalid`：解析失败或超出合理范围
- `estimated`：估算值（必须标注方法）

## 验收清单（Phase 1）

- [ ] FRED 序列返回值和最新观测日期正确，缺少 API key 时有明确提示
- [ ] 黄金现货/期货、ETF 的产品类型/时区/日期口径没有混淆
- [ ] 所有数据适配器有 mock/fixture 测试，解析失败不会静默输出旧数据
- [ ] 缺失值、过期值、异常值都被标记，绝不自动填 0
- [ ] 同一日期重复运行可去重且结果可复现
- [ ] 每日报告中每条核心数字都有来源和观测日期
- [ ] 运行失败时保留最近有效数据，并在 Actions Summary 明示失败原因
- [ ] README 说明如何配置 `FRED_API_KEY`、如何手动补跑

## 免责声明

本项目仅供研究与信息整理，不构成任何投资建议。报告中的解释与推测均为作者个人分析框架，读者应自行核实原始数据并独立判断。
