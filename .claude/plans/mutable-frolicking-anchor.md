# 飞书多维表格 + 本地数据库 交易系统升级

## Context

当前 `stock_analysis` 系统的数据以 JSON 文件散落在 `D:\1989n\stock_data\`，展示靠终端 print 和飞书 Webhook 文本推送。问题是：
- JSON 文件之间无关联，查不了"持仓股今天的新闻"
- 飞书推送是纯文本，密密麻麻看不到重点
- 没有仪表盘/看板等一目了然的视图

目标：底层用 SQLite 做结构化存储（数据主权在本地），上层用飞书多维表格做展示（看板/图表/手机随时看），中间用同步桥接关联。

## 架构

```
本地 SQLite (stock.db)                  飞书多维表格 (展示层)
├── stocks         ────sync───>  表1: 持仓驾驶舱 (看板+图表)
├── portfolio      ────sync───>  表2: 行情监控 (表格视图)
├── market_data    ────sync───>  表3: 财经快讯 (表格+日历)
├── hot_stocks     ────sync───>  表4: 财报日历 (表格+甘特图)
├── news
└── financials
       │
feishu_table_sync.py  ← 新增的同步桥接
daily_task.py         ← 现有，改造后先写 SQLite 再触发同步
```

## 实施步骤

### Step 1: 建本地 SQLite 数据库 (`database.py`)

新建 `stock_analysis/database.py`，用 Python sqlite3 模块：

```sql
-- 股票主表
CREATE TABLE stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT,
    market TEXT,          -- SH/SZ/BJ
    list_date TEXT
);

-- 持仓表
CREATE TABLE portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT REFERENCES stocks(code),
    shares INTEGER NOT NULL,
    cost REAL NOT NULL,
    entry_date TEXT,
    updated TEXT
);

-- 行情数据 (每日快照)
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT REFERENCES stocks(code),
    date TEXT NOT NULL,
    price REAL,
    change_pct REAL,
    volume REAL,
    amount REAL,
    turnover_rate REAL,
    pe REAL,
    market_cap REAL,
    UNIQUE(stock_code, date)
);

-- 热门股票 (每日排行)
CREATE TABLE hot_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    stock_name TEXT,
    rank INTEGER,
    price REAL,
    change_pct REAL,
    volume REAL,
    amount REAL,
    turnover_rate REAL,
    pe REAL,
    market_cap REAL,
    sources TEXT,          -- JSON array
    date TEXT NOT NULL
);

-- 新闻
CREATE TABLE news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source TEXT,
    url TEXT,
    sentiment TEXT,        -- 利好/利空/中性
    related_stocks TEXT,   -- JSON array of stock codes
    category TEXT,         -- 宏观政策/行业动态/个股公告
    pub_time TEXT,
    collected_at TEXT
);

-- 财报数据
CREATE TABLE financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT REFERENCES stocks(code),
    report_period TEXT,    -- 2026Q1
    report_type TEXT,      -- income/balance/cash_flow
    data JSON,             -- 完整报表数据 JSON
    collected_at TEXT
);
```

提供函数：`init_db()`, `insert_stock()`, `upsert_market_data()`, `get_portfolio_with_quotes()` 等。

### Step 2: 改造数据采集，写入 SQLite

修改 `sources/hot_stocks.py` 和 `modules/*.py` 的保存逻辑：
- 保留 `save_output()` 写 JSON（兼容现有）
- 新增：同步写入 SQLite（通过 `database.py`）
- 在 `daily_task.py` 末尾触发飞书同步

### Step 3: 建飞书多维表格同步桥接 (`feishu_table_sync.py`)

新增文件，核心逻辑：
1. 从 SQLite 读取最新数据
2. 通过飞书开放平台 API 写入多维表格
3. 全量同步策略：每次同步前清空表，重新写入（简单可靠）

飞书 API 调用链：
```
获取 tenant_access_token
  → 列出多维表格的表
    → 批量创建/更新记录
```

**表1: 持仓驾驶舱**
| 字段 | 类型 | 来源 |
|------|------|------|
| 代码 | 文本 | portfolio.stock_code |
| 名称 | 文本 | stocks.name |
| 行业 | 单选 | stocks.industry |
| 持仓数量 | 数字 | portfolio.shares |
| 成本价 | 数字 | portfolio.cost |
| 最新价 | 数字 | market_data.price (latest) |
| 市值 | 公式 | shares × price |
| 盈亏% | 公式 | (price - cost) / cost × 100 |
| 今日涨跌% | 查找引用 | market_data.change_pct |

视图：表格视图(默认) + 看板视图(按行业分组，卡片显示盈亏%)

**表2: 行情监控**
| 字段 | 类型 | 来源 |
|------|------|------|
| 代码 | 文本 | hot_stocks |
| 名称 | 文本 | hot_stocks |
| 最新价 | 数字 | hot_stocks |
| 涨跌幅% | 数字 | hot_stocks |
| 成交量(万手) | 数字 | hot_stocks |
| 换手率% | 数字 | hot_stocks |
| 排名 | 数字 | hot_stocks |
| 上榜原因 | 多选 | hot_stocks.sources |

视图：表格视图 + 仪表盘(涨跌分布饼图、涨幅排行榜)

**表3: 财经快讯**
| 字段 | 类型 | 来源 |
|------|------|------|
| 标题 | 文本 | news |
| 来源 | 单选 | news |
| 情感 | 单选(利好/利空/中性) | news |
| 分类 | 单选 | news |
| 关联股票 | 文本 | news |
| 发布时间 | 日期 | news |

**表4: 财报日历**
| 字段 | 类型 | 来源 |
|------|------|------|
| 代码 | 文本 | financials |
| 报告期 | 文本 | financials |
| 报表类型 | 单选 | financials |
| 关键数据 | 文本(摘要) | financials.data |

### Step 4: 写入飞书多维表格

飞书 API 写入需要：
1. 先在飞书手动创建多维表格，获取 `app_token` 和各表 `table_id`
2. 配置到 `.env` 中
3. `feishu_table_sync.py` 通过 API 批量写入记录

首次在飞书端手动建表（5分钟），之后脚本自动同步。

### Step 5: 定时调度

修改 `run_hot_stocks.bat`，采集完成后自动触发飞书同步。
或通过 Claude Code cron 定时执行。

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `database.py` | **新建** | SQLite 数据库层 |
| `feishu_table_sync.py` | **新建** | 飞书多维表格同步桥接 |
| `modules/market.py` | 修改 | 采集后同步写 SQLite |
| `sources/hot_stocks.py` | 修改 | 采集后同步写 SQLite |
| `daily_task.py` | 修改 | 末尾触发飞书同步 |
| `.env.example` | 修改 | 增加飞书多维表格配置项 |
| `config.py` | 修改 | 增加数据库路径配置 |

## 验证方式

1. 运行 `python database.py` — 建库成功，表结构正确
2. 运行 `python sources/hot_stocks.py 10` — 数据写入 SQLite + JSON 双写
3. 运行 `python feishu_table_sync.py` — 数据推送到飞书多维表格
4. 打开飞书多维表格 — 数据可见，视图正确
