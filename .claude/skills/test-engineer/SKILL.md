---
name: test-engineer
description: 关键路径要有证据 — 找出最值得补的测试，提供验证方案和数据
origin: 1989n
---

# Test Engineer

> 不追求全覆盖，在**最有价值的位置补测试**，让关键路径有证据可用。
>
> 测试的是**行为**不是**实现**。测试和实现细节强耦合 → 重构时会碎 → 不如不写。

## 路径价值分级

| 等级 | 出错后果 | 需要测试？ |
|------|---------|-----------|
| critical | 发飞书错误数据 / 发不出去 | **必须**有测试 |
| high | 分析结论偏差 / 数据不完整 | 尽量有 |
| medium | 系统降级但能运行 | 有最好 |

## 项目专属：关键路径分级

### Critical（必须覆盖）

1. **涨停池数据转换** (`daily_task.py:fetch_hot_stocks_zt_pool`)
   - akshare 列名/格式随时可能变
   - 输出必须是统一的 `[{code, name, ...}]` 格式
   - 测试：mock akshare 返回值，验证转换逻辑

2. **数据保鲜判定** (`data_quality_gate.py:freshness_check`)
   - age > max_hours → stale 判定
   - 边界：文件不存在、age == max_hours
   - 测试：纯函数，给 mtime + now 算 age，验证 pass/fail

3. **持仓加载** (`portfolio.json` 解析)
   - 持仓数据错误 = 分析全错
   - 测试：给定标准 portfolio.json，验证能正确解析

### High（尽量覆盖）

4. **Grader 评分逻辑** (`experts/grader.py`)
   - 置信度评分逻辑、降级条件
   - 测试：给标准输入，验证 scores < 0.5 时正确阻断

5. **飞书路由** (`feishu_sender.py`)
   - FEISHU_ROUTES 配置解析、chat_id 映射
   - 测试：mock 环境变量，验证路由逻辑

### Medium（有最好）

6. **conversation_miner JSONL 解析**
   - type=user/assistant/queue-operation 结构差异
   - 空行、注释行处理

## 明确不测

| 场景 | 为什么 |
|------|--------|
| schtasks + BAT 调度层 | 集成测试成本 > bug 频率 |
| DeepSeek API 调用 | 外部依赖，mock 无意义 |
| feishu HTTP 请求 | 外部依赖 |
| 稳定的纯查询脚本 | 改了再补 |

## 测试策略

```
stock_analysis/tests/
  test_data_quality_gate.py
  test_hot_stocks_pipeline.py
  test_portfolio_loader.py
  test_grader.py
```
运行：`/d/Python314/python -m pytest stock_analysis/tests/ -v`

## 验证证据

每次补测后输出：
1. 新增哪些测试文件/用例
2. 发现了什么问题（如果有）
3. 跑通证据（pytest 输出）
4. 还有哪些已知盲区
