#!/usr/bin/env python3
"""Claude Code status line generator."""
import sys, json, os
from datetime import datetime

try:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}

model = data.get("model", data.get("current_model", os.environ.get("ANTHROPIC_MODEL", "DeepSeek")))
tokens = data.get("total_tokens", data.get("tokens_used", 0))
cost = data.get("total_cost_usd", data.get("cost_usd", 0))
now = datetime.now().strftime("%H:%M")

parts = [model, now]
if tokens:
    parts.append(f"{tokens // 1000}k tk")
if cost:
    parts.append(f"${cost:.3f}")

print("  " + "  |  ".join(parts))
sys.exit(0)
