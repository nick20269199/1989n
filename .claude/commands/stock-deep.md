---
name: stock-deep
description: 个股深度分析 — 财务三表+估值+盈利预测+研报+股东，完整基本面研究
allowed_tools: ["mcp__china-stock__get_balance_sheet", "mcp__china-stock__get_income_statement", "mcp__china-stock__get_cash_flow", "mcp__china-stock__get_financial_metrics", "mcp__china-stock__get_stock_value", "mcp__china-stock__get_profit_forecast", "mcp__china-stock__get_stock_research_report", "mcp__china-stock__get_shareholder_info", "mcp__china-stock__get_stock_basic_info", "mcp__china-stock__get_stock_fhps_detail", "mcp__china-stock__get_product_info", "mcp__china-stock__get_inner_trade_data"]
---

# /stock-deep <股票代码> — 个股深度基本面分析

完整财务分析，适合选股决策和持仓评估。

## 用法

```
/stock-deep 002156           # 深度分析通富微电
/stock-deep 000858           # 深度分析五粮液
```

## 执行步骤

### 第一步：并行获取全部基础数据（一次发出所有调用）

```
mcp__china-stock__get_stock_basic_info     # 基本信息
mcp__china-stock__get_balance_sheet        # 资产负债表
mcp__china-stock__get_income_statement     # 利润表
mcp__china-stock__get_cash_flow            # 现金流量表
mcp__china-stock__get_financial_metrics    # 关键财务指标
mcp__china-stock__get_stock_value           # 估值分析
mcp__china-stock__get_profit_forecast       # 业绩预测
mcp__china-stock__get_stock_research_report # 券商研报
mcp__china-stock__get_shareholder_info      # 股东情况
mcp__china-stock__get_stock_fhps_detail     # 分红配送
mcp__china-stock__get_product_info          # 主营业务构成
mcp__china-stock__get_inner_trade_data      # 高管增减持
```

### 第二步：按以下模板输出深度报告

```markdown
# {股票名称} ({代码}) 深度分析

## 一、公司概况
- 行业 / 上市日期 / 总市值 / 流通市值
- 主营业务构成（产品+营收占比）

## 二、财务健康度

### 利润表（最近3期）
| 报告期 | 营业收入(亿) | 归母净利润(亿) | 同比增速 | EPS | ROE |
|--------|-------------|---------------|---------|-----|-----|

### 资产负债表（最近3期）
| 报告期 | 总资产(亿) | 总负债(亿) | 净资产(亿) | 资产负债率 |
|--------|-----------|-----------|-----------|-----------|

### 现金流（最近3期）
| 报告期 | 经营CF(亿) | 投资CF(亿) | 筹资CF(亿) | 自由现金流 |
|--------|-----------|-----------|-----------|-----------|

### 关键指标趋势
- 毛利率 / 净利率 / ROE / ROA 变化趋势
- 营收增速 vs 利润增速
- 经营现金流/净利润比值（>1 为健康）

## 三、估值分析
- 当前PE / PE分位 / 行业PE均值
- PB / PS
- 估值水位判断（低估/合理/高估）

## 四、盈利预测
| 预测年份 | 预测净利润(亿) | 预测EPS | 预测PE | 机构数 |
|----------|---------------|---------|--------|--------|

## 五、机构态度
- 最近研报标题+评级+券商+日期（取最近5篇）
- 评级分布（买入/增持/中性/减持）

## 六、股东结构
- 前十大股东及持股变化
- 股东人数趋势（集中/分散）
- 高管增减持情况

## 七、分红记录
- 最近3年分红方案
- 股息率

## 八、综合评价（5维度评分，每项1-10分）

| 维度 | 评分 | 说明 |
|------|------|------|
| 成长性 | X | 营收/利润增速 |
| 盈利质量 | X | ROE/现金流/毛利 |
| 估值性价比 | X | PE分位/成长匹配 |
| 机构认可度 | X | 研报/预测/股东 |
| 财务安全 | X | 负债率/现金流 |

### 总结
- 核心优势（1-2点）
- 主要风险（1-2点）
- 适合策略（长期/波段/短期）
```
