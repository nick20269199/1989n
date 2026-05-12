# 轻量级数据校验 /verify-data

> 每次对话启动自动跑。30秒内完成，只问三个问题：数据源活着吗？持仓有变化吗？脚本报错了吗？
> 不是分析，是健康检查。

## 触发时机

**自动触发（CLAUDE.md规则）**:
- 每个交易日首次对话启动时，自动执行
- 重要操作（清仓/加仓/开新仓）后，自动执行

**手动触发**:
- `/verify-data` — 任何时候想检查

## 执行流程（三步，每步调用现有脚本）

### Step 1: 数据源健康（5s）

```bash
cd d:/1989n/stock_analysis && python -c "
from data_source_router import check_channels
status = check_channels()
for ch, ok in status.items():
    print(f'{ch}: {\"OK\" if ok else \"FAIL\"}')
"
```

通道: sina_stock, sina_index, tencent, sohu_kline, eastmoney
至少有一个可用就算绿色。全挂就标红色。

### Step 2: 持仓快照（10s）

```bash
cd d:/1989n/stock_analysis && python stock_quote.py check
```

读出当前持仓名称 + 实时价 + 盈亏%，与 portfolio.json 对比。
如果 cost 与 memory 记录不一致 → 标记并报告。

### Step 3: 错误检查（5s）

```bash
# 读 last_error.txt 最后修改时间和内容
# 读 data_guard.py 最新运行日志
# 检查 closing_review.json / morning_enhanced.json 最近修改时间是否超过24h
```

## 输出格式

正常的交易日输出只需一句话：

> ✅ 数据正常 | 通富-2.9% 多氟多-4.3% 天银-6.1% | 7只持仓 数据源新浪

有问题才展开：

> ⚠️ 发现 N 个问题:
> 1. [高位] 明阳电路成本47.76现价30.0, 硬止损-37.4%已触发
> 2. [中位] 多氟多临近软止损-6.3%
> 3. [低位] last_error.txt 有未处理报错（XXX）

## 硬约束

- **总耗时不超过30秒**。超时自动截断，已查到的信息照出。
- 只调用 `data_source_router.py`、`stock_quote.py`、读JSON文件。不跑完整 `daily_task.py` 模式。
- 不输出分析/建议，只出数字和状态标记。
- 发现硬止损触发（明阳电路-37.4%）→ 第一段就报告，不压底。
