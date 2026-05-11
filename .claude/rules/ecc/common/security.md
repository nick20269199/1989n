# 安全

## 改前备份

修改 rules/、memory/、CLAUDE.md、定时任务配置 → 先备份到 `~/.claude/backups/YYYYMMDD_HHMM/`

## 密钥

```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.environ["API_KEY"]  # 缺了直接崩，别给默认值
```

## 出事

密钥泄露 → 立即轮换 → 查全库有没有同类问题
