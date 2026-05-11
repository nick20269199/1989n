# Stock KB — 股票知识库

> 位置: D:\1989n\stock_kb
> 创建: 2026-05-04

## 目录结构

```
stock_kb/
├── README.md                    # 本文件
├── portfolio/                   # 持仓管理 ✅
│   ├── snapshots/               # 每日持仓快照 (JSON)
│   │   └── 2026-05-04.json      # 6只标的，总资产246,653
│   └── changes.jsonl            # 变动日志
├── daily/                       # 每日数据 ✅
│   ├── news/                    # 财经新闻采集
│   │   └── 2026-05-04.json      # 50条新闻+持仓影响分析
│   ├── quotes/                  # 行情快照
│   │   └── 2026-05-04.json      # 6只持仓实时行情
│   └── reports/                 # 每日分析报告
│       └── 2026-05-04.md        # 持仓诊断+板块影响+操作建议
├── research/                    # 深度研究 ✅
│   ├── stocks/                  # 个股深度分析 (6只)
│   │   ├── 002156_通富微电.md
│   │   ├── 000062_深圳华强.md
│   │   ├── 300739_明阳电路.md
│   │   ├── 300480_光力科技.md
│   │   ├── 000815_美利云.md
│   │   └── 002261_拓维信息.md
│   └── sectors/                 # 行业/板块分析
│       └── 2026-05-04.md        # Top10板块+持仓关联
├── screens/                     # 选股系统 ✅
│   ├── conditions/              # 选股条件定义
│   │   └── default.json         # 4维度评分框架
│   └── results/                 # 选股结果 (待填充)
└── qa_log/                      # 问答日志 ✅
    └── 2026-05.jsonl            # 4条Q&A记录
```

## 数据流

1. **每日采集** → `daily/news/` + `daily/quotes/`
2. **持仓变动** → `portfolio/snapshots/` (每日快照) + `portfolio/changes.jsonl` (变动记录)
3. **深度分析** → `research/stocks/` + `research/sectors/`
4. **问答记录** → `qa_log/`
5. **选股** → `screens/conditions/` (条件) → `screens/results/` (结果)
