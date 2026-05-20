---
name: debugger
description: 复现步骤 → 定位根因 → 最小修复，不靠猜不闷头重试。TRIGGER when: 用户说"报错了"/"出错了"/"崩了"/"挂了"/"跑不起来"、last_error.txt 有内容、脚本非零退出、构建失败。DO NOT TRIGGER when: 用户明确说"没事"、已知预期错误。
origin: 1989n
---

# Debugger

> 用**系统化的方法定位根因**，不在日志里瞎翻或闷头重试。
>
> 铁律：**先查配置/权限，不闷头重试**（根因诊断原则）。

## 通用调试流程

每一轮必须按这个顺序走完，跳步 → 漏根因：

```
观察症状 → 缩小范围 → 定位根因 → 最小修复 → 验证修复
```

### 层状排查法（从外到内）

```
用户反馈错误
  ↓
Scheduler 层 → schtasks 状态？上次运行结果？
  ↓
BAT 包装层 → BAT 能手动跑通？日志有记录？
  ↓
Python 入口 → 脚本直接跑有一样错误？
  ↓
数据层 → 输入文件存在且有内容？API 返回正确？
  ↓
逻辑层 → 哪行代码抛异常？哪个条件分支走了预期外路径？
  ↓
输出层 → 输出了什么？飞书发了什么？
```

### 根因定位四问

1. **最近改了什么？** — git diff / 文件修改时间
2. **是不是没变但是外部变了？** — API 格式、数据内容、依赖版本
3. **是不是间歇性的？** — 看多轮运行模式
4. **用手工能复现吗？** — 最小复现步骤

### 最小修复原则

- 只修根因，不修周边
- 修复附带一个断言/校验防止同类问题再发生
- 不改风格、不重构、不加功能

## 项目专属：故障模式速查

### 故障 1：定时任务不跑

**排查：** `schtasks /Query /TN "\任务名" /FO CSV /V`
- 状态不是"就绪" → 任务被禁用/删除了
- Last Result != 0 → 执行出错
- 看 `stock_data/cognitive_agent.log`

**已踩坑：**
- Windows 更新后 schtasks 丢失
- BAT 路径 `\1` 被解释为转义 → 用 pathlib
- Python 解释器路径不对 → 确认 `/d/Python314/python`

### 故障 2：飞书消息没发

**排查：**
```
1. Python 日志 → send_feishu_message 返回 True/False
2. FEISHU_ROUTES 配置 → chat_id 对不对
3. 看飞书群 → 发了但路由错了
4. webhook URL 是否过期
```

**已踩坑：** chat_id 映射错误、webhook token 过期、消息含换行符截断

### 故障 3：数据过期

**排查：**
```bash
ls -la stock_data/hot_stocks.json
python -c "import json; d=json.load(open('stock_data/hot_stocks.json')); print(len(d), '条')"
python -c "from data_quality_gate import preflight_scan; print(preflight_scan(['hot_stocks.json'])['summary'])"
```

### 故障 4：DeepSeek API 失败

**排查：** 6 通道 API key 是否有效？余额够？返回什么错误码？

**已踩坑：** key 过期、超时、内容过滤

### 日志索引

| 日志 | 内容 |
|------|------|
| `stock_data/cognitive_agent.log` | 大部分 Python 脚本输出 |
| `stock_data/morning_brief.log` | 晨报日志 |
| `stock_data/closing_review.log` | 收盘复盘 |
| `stock_data/hot_stocks.log` | 热门股票采集 |

## 修复输出格式

```
## 故障: [标题]
- 症状:
- 排查路径:
- 根因:
- 修复:
- 验证:
- 预防:
```
