"""
DeepSeek multi-channel router — 六通道独立配额，agent/主会话互不抢占。

Channel 1 (主会话):  Claude Code 专用，不进这个模块
Channel 2 (研究):    deep-research agent 后台深挖
Channel 3 (并行):    辅助任务 / fallback
Channel 4 (盘中):    盘中实时分析
Channel 5 (复盘):    收盘复盘分析
Channel 6 (新闻):    新闻资讯处理

用法:
    from deepseek_multi import research, intraday, review, news
    result = research("深度分析某个问题...")
"""
import json
import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("deepseek_multi")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
}

# 通道配置
CHANNELS = {
    "research": {
        "key": os.getenv("DEEPSEEK_API_KEY_RESEARCH", ""),
        "model": "deepseek-chat",
        "description": "后台深度研究",
    },
    "parallel": {
        "key": os.getenv("DEEPSEEK_API_KEY_PARALLEL", ""),
        "model": "deepseek-chat",
        "description": "并行辅助任务",
    },
    "intraday": {
        "key": os.getenv("DEEPSEEK_API_KEY_INTRADAY", ""),
        "model": "deepseek-chat",
        "description": "盘中实时分析",
    },
    "review": {
        "key": os.getenv("DEEPSEEK_API_KEY_REVIEW", ""),
        "model": "deepseek-chat",
        "description": "收盘复盘分析",
    },
    "news": {
        "key": os.getenv("DEEPSEEK_API_KEY_NEWS", ""),
        "model": "deepseek-chat",
        "description": "新闻资讯处理",
    },
}

SYSTEM_RESEARCH = """你是一位A股市场深度研究员。你的任务是对给定的问题进行深入分析。

要求：
- 第一性原理思考：从最基本的事实出发推导，不依赖二手结论
- 因果推理：区分相关性和因果性，明确标注哪些是确定的因果关系、哪些是观察到的相关性
- 反事实检验：对每个关键判断，追问"如果相反的情况发生，会看到什么信号"
- 不确定性标注：明确区分"已确认的事实"、"有证据支持的推断"、"待验证的假设"
- 量化约束：涉及数字时必须给出具体数值范围，禁止"较高""偏低"等模糊描述
- 可验证性：每个结论必须说明可以通过什么数据来验证

语言：中文。简洁，不写套话。"""

REQUEST_TIMEOUT = 120


def _call(channel: str, prompt: str, system: str = SYSTEM_RESEARCH,
          temperature: float = 0.3, max_tokens: int = 4096) -> str:
    """通过指定通道调用 DeepSeek API。"""
    cfg = CHANNELS.get(channel)
    if not cfg or not cfg["key"]:
        return f"[通道 {channel} 未配置]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    headers = {**HEADERS_TEMPLATE, "Authorization": f"Bearer {cfg['key']}"}
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        r = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.Timeout:
        logger.error(f"Channel {channel} timed out after {REQUEST_TIMEOUT}s")
        return f"[通道 {channel} 超时]"
    except Exception:
        logger.exception(f"Channel {channel} failed")
        return f"[通道 {channel} 调用失败]"


def research(prompt: str, **kwargs) -> str:
    """Channel 2 — 后台深度研究。独立配额，不影响主会话。"""
    return _call("research", prompt, **kwargs)


def parallel_analyze(prompt: str, **kwargs) -> str:
    """Channel 3 — 并行辅助任务。"""
    return _call("parallel", prompt, **kwargs)


def intraday(prompt: str, **kwargs) -> str:
    """Channel 4 — 盘中实时分析。独立配额。"""
    return _call("intraday", prompt, **kwargs)


def review(prompt: str, **kwargs) -> str:
    """Channel 5 — 收盘复盘分析。独立配额。"""
    return _call("review", prompt, **kwargs)


def news_analyze(prompt: str, **kwargs) -> str:
    """Channel 6 — 新闻资讯处理。独立配额。"""
    return _call("news", prompt, **kwargs)


def dual_research(prompt: str) -> dict:
    """双通道并行研究同一问题，合并结果。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_r = executor.submit(research, prompt)
        f_p = executor.submit(parallel_analyze, prompt)
        results["research"] = f_r.result()
        results["parallel"] = f_p.result()

    return results


def channel_health() -> dict:
    """检查所有通道的连通性。"""
    status = {}
    for name, cfg in CHANNELS.items():
        if not cfg["key"]:
            status[name] = {"ok": False, "error": "未配置 API Key"}
            continue
        try:
            headers = {**HEADERS_TEMPLATE, "Authorization": f"Bearer {cfg['key']}"}
            r = requests.get(
                "https://api.deepseek.com/v1/models",
                headers=headers,
                timeout=10,
            )
            status[name] = {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:
            status[name] = {"ok": False, "error": str(e)}
    return status


if __name__ == "__main__":
    # 健康检查
    print(json.dumps(channel_health(), indent=2, ensure_ascii=False))
