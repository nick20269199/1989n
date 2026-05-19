"""
Dual-model AI router — DeepSeek + Qwen 多通道并行推理。
DeepSeek 6通道 (deepseek_multi.py) + Qwen 3通道。
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

from config import (
    DASHSCOPE_API_KEY, DASHSCOPE_API_KEY_RESEARCH, DASHSCOPE_API_KEY_PARALLEL,
    DEEPSEEK_API_KEY, HEADERS,
)

logger = logging.getLogger("ai_router")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
QWEN_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

DEEPSEEK_MODEL = "deepseek-chat"
QWEN_MODEL = "qwen-plus"

# Qwen 通道配置
QWEN_CHANNELS = {
    "primary": {
        "key": DASHSCOPE_API_KEY,
        "model": QWEN_MODEL,
        "description": "主分析通道 (ai_router / vision)",
    },
    "research": {
        "key": DASHSCOPE_API_KEY_RESEARCH,
        "model": QWEN_MODEL,
        "description": "辅助分析 (research)",
    },
    "parallel": {
        "key": DASHSCOPE_API_KEY_PARALLEL,
        "model": QWEN_MODEL,
        "description": "并行任务 (parallel / fallback)",
    },
}

SYSTEM_PROMPT = """你是一位A股价值投资分析助手，为一个管理投资组合的投资者提供支持。
你可以访问以下数据：
- 技术指标：MA均线、MACD、RSI、VCP形态
- 市场情绪：StockAPI 情绪周期数据（上涨比例、涨停跌停家数、大肉/大面情绪）
- 实时行情和新闻

请用中文回答，简洁专业。涉及具体股票时请提醒：分析仅供参考，不构成投资建议。"""

REQUEST_TIMEOUT = 60


def query_deepseek(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Call DeepSeek Chat API for reasoning."""
    if not DEEPSEEK_API_KEY or "your-deepseek-key" in DEEPSEEK_API_KEY:
        return "[DeepSeek 未配置]"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 4096},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("DeepSeek query failed")
        return "[DeepSeek 调用失败]"


def query_qwen(prompt: str, history: Optional[list[dict]] = None, channel: str = "primary") -> str:
    """Call Qwen/DashScope API. channel: primary / research / parallel."""
    cfg = QWEN_CHANNELS.get(channel, QWEN_CHANNELS["primary"])
    key = cfg["key"]
    if not key:
        return f"[千问 {channel} 未配置]"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            QWEN_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"model": cfg["model"], "messages": messages, "temperature": 0.7, "max_tokens": 4096},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        logger.exception(f"Qwen {channel} query failed")
        return f"[千问 {channel} 调用失败]"


def query_qwen_research(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Channel 2 — 千问辅助分析。独立配额。"""
    return query_qwen(prompt, history, channel="research")


def query_qwen_parallel(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Channel 3 — 千问并行任务。独立配额。"""
    return query_qwen(prompt, history, channel="parallel")


def dual_analyze(prompt: str) -> str:
    """Run both models in parallel and merge results.

    DeepSeek → reasoning / logic
    Qwen     → financial analysis / Chinese response
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_ds = executor.submit(query_deepseek, prompt)
        future_qw = executor.submit(query_qwen, prompt)

        deepseek_result = future_ds.result()
        qwen_result = future_qw.result()

    has_ds = not deepseek_result.startswith("[DeepSeek")
    has_qw = not qwen_result.startswith("[千问")

    parts: list[str] = []

    if has_ds and has_qw:
        parts.append(f"**DeepSeek 推理**:\n{deepseek_result}\n")
        parts.append(f"**千问 分析**:\n{qwen_result}")
    elif has_qw:
        parts.append(qwen_result)
    elif has_ds:
        parts.append(deepseek_result)
    else:
        parts.append("两个模型当前都不可用，请检查 API Key 配置。")

    return "\n\n".join(parts)


def qwen_health() -> dict:
    """检查所有千问通道连通性。"""
    status = {}
    for name, cfg in QWEN_CHANNELS.items():
        key = cfg["key"]
        if not key:
            status[name] = {"ok": False, "error": "未配置 API Key"}
            continue
        try:
            r = requests.get(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            status[name] = {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:
            status[name] = {"ok": False, "error": str(e)}
    return status


if __name__ == "__main__":
    print("=== DeepSeek 通道 ===")
    from deepseek_multi import channel_health as ds_health
    print(json.dumps(ds_health(), indent=2, ensure_ascii=False))
    print("\n=== Qwen 通道 ===")
    print(json.dumps(qwen_health(), indent=2, ensure_ascii=False))
