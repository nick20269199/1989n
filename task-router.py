#!/usr/bin/env python3
"""最小可行任务路由器 — 危险词检查"""
import sys, re

DANGER_WORDS = ["删除", "修改配置", "执行交易", "发送飞书", "DROP"]

def match_task(description: str):
    for word in DANGER_WORDS:
        if re.search(re.escape(word), description, re.IGNORECASE):
            return {"status": "blocked", "reason": f"检测到危险词: {word}"}
    return {"status": "allow_direct", "reason": "未检测到危险词"}

if __name__ == "__main__":
    desc = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    result = match_task(desc)
    print(f"status:{result['status']}")
