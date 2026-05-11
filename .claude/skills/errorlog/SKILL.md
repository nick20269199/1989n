---
name: errorlog
description: 报错原文捕获 — 当用户描述"报错了"但没贴原始报错时,直接读取 last_error.txt 获取完整英文 traceback,不让用户转述。
origin: stock_analysis
---

# 报错原文捕获 (Error Log)

> **核心原则**: 不让英语不好的人翻译报错。Claude 自己去读原始错误文件。

## 触发时机

**必须触发** (Claude 检测到以下模式时立即执行 Step 1):
- 用户说"报错了"、"出错了"、"跑不起来"、"挂了"、"崩了"
- 用户说"有个错误"、"error"、"不对了"、"有问题"
- 用户用自己的话描述了一个错误但没有附带英文原文

**此时 Claude 的硬反应**: 不要直接修。先去读 `D:/1989n/stock_data/last_error.txt`。

## 工作流

### Step 1: 读取原始报错

```bash
cat D:/1989n/stock_data/last_error.txt
```

如果文件存在且包含有效 traceback → 基于原文诊断。
如果文件不存在或太旧(>24h) → 问用户："能帮我跑一下刚才那命令，然后把终端里出现的英文原文贴过来吗？"

### Step 2: 翻译解释 (给用户看的)

读完英文报错后，用中文告诉用户:
1. **这是什么错误** — 一句话中文解释
2. **发生在哪** — 哪个文件的第几行
3. **可能原因** — 1-2 种最可能的原因
4. **修复方案** — 具体改什么

### Step 3: 修复

执行修复。修完后：
```bash
python D:/1989n/stock_analysis/error_capture.py  # 验证修复
```

## 如何让所有脚本自动捕获错误

在每个定时任务的 .py 文件开头加一行：

```python
from error_capture import trap; trap()
```

已接入的脚本:
- (按需添加，每加一个在这行下面记录)

## 反模式

- ❌ 用户说"有个 TypeError" → Claude 直接猜原因开始修 (应该先读 last_error.txt)
- ❌ 用户用自己的话描述报错 → Claude 接受转述并基于转述修 (转述必有信息损失)
- ❌ last_error.txt 里的错误和当前问题不是同一个 → 让用户重新跑命令更新错误文件
