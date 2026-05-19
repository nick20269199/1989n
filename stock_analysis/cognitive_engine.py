"""
cognitive_engine.py — DeepSeek 认知引擎

定时认知任务统一后端：
  1. 加载 memory/ 知识上下文构建 system prompt
  2. 加载实时数据
  3. 调用 DeepSeek API 推理
  4. 产出落地 + 飞书推送

用法:
    from cognitive_engine import deepseek_reason, load_context

    数据 = {...}  # 自己采集
    上下文 = load_context(["knowledge/stocks/xxx.md"])
    结果 = deepseek_reason("review", 上下文 + "\\n\\n" + json.dumps(数据))
    send_output("task_name", 结果, "news")
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from deepseek_multi import research, parallel_analyze, intraday, review, news_analyze
from feishu_sender import send_feishu_message

logger = logging.getLogger("cognitive_engine")

CST = timezone(timedelta(hours=8))
MEMORY_DIR = Path("D:/1989n/.claude/memory")
STOCK_DATA = Path("D:/1989n/stock_data")

# ── 通道映射：任务名 → (DeepSeek通道函数, 用途) ──
CHANNEL_MAP = {
    "research":  research,
    "parallel":  parallel_analyze,
    "intraday":  intraday,
    "review":    review,
    "news":      news_analyze,
}


def load_context(file_paths: list[str]) -> str:
    """从 memory/ 加载知识文件，拼接为 system context。

    Args:
        file_paths: 相对 MEMORY_DIR 的路径列表
                    e.g. ["knowledge/stocks/morning-brief-architecture.md"]

    Returns:
        拼接后的文本，包含文件名标题和内容
    """
    sections = []
    sections.append("## 系统知识上下文\n")

    for rel_path in file_paths:
        full = MEMORY_DIR / rel_path
        if not full.exists():
            logger.warning(f"上下文文件不存在: {full}")
            continue

        try:
            content = full.read_text(encoding="utf-8")
            # 去掉 frontmatter（--- 之间的部分）
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
            sections.append(f"--- {rel_path} ---\n{content}")
        except Exception as e:
            logger.warning(f"读取上下文失败 {rel_path}: {e}")

    return "\n\n".join(sections)


def load_portfolio() -> dict:
    """加载当前持仓（从 memory/user/portfolio.md 解析）。

    Returns:
        {"code": {"name": str, "shares": int, "cost": float}, ...}
        或空 dict
    """
    portfolio_file = MEMORY_DIR / "user" / "portfolio.md"
    if not portfolio_file.exists():
        return {}
    # 简单解析 frontmatter 中的持仓信息，返回占位
    # 实际需按你的 portfolio.md 格式解析
    return {}


def deepseek_reason(
    channel: str,
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """调用 DeepSeek 通道做推理。

    Args:
        channel: "research" / "parallel" / "intraday" / "review" / "news"
        prompt: 用户提示（含数据 + 指令）
        system_prompt: 可选的 system prompt 覆盖

    Returns:
        DeepSeek 响应文本，或错误提示（调用失败时）
    """
    func = CHANNEL_MAP.get(channel)
    if not func:
        return f"[错误] 未知通道: {channel}，可选: {list(CHANNEL_MAP.keys())}"

    logger.info(f"[{channel}] 发送推理请求 ({len(prompt)} chars)...")

    kwargs = {"temperature": temperature, "max_tokens": max_tokens}
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        result = func(prompt, **kwargs)
        logger.info(f"[{channel}] 推理完成 ({len(result)} chars)")
        return result
    except Exception as e:
        logger.exception(f"[{channel}] 推理失败")
        return f"[错误] DeepSeek 调用失败: {e}"


def send_output(
    task_name: str,
    content: str,
    route: str = "main",
    title: str = "",
) -> bool:
    """将任务产出发送到飞书。

    Args:
        task_name: 任务名，用于日志
        content: Markdown 内容
        route: 飞书路由名称 (config.FEISHU_ROUTES 中的 key)
        title: 消息标题，默认用 "{task_name} | {日期}"

    Returns:
        是否发送成功
    """
    if not title:
        today = datetime.now(CST).strftime("%Y-%m-%d")
        title = f"{task_name} | {today}"

    return send_feishu_message(title, content, chat_id=route)


def save_output(task_name: str, content: str, filename: str = "") -> Path:
    """将产出保存到 stock_data/。

    Args:
        task_name: 任务名，用于目录
        content: 内容
        filename: 文件名，默认 "{task_name}_{YYYYMMDD_HHMM}.md"

    Returns:
        保存的文件路径
    """
    if not filename:
        ts = datetime.now(CST).strftime("%Y%m%d_%H%M")
        filename = f"{task_name}_{ts}.md"

    out_dir = STOCK_DATA / "cognitive_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / filename
    out_path.write_text(content, encoding="utf-8")
    logger.info(f"产出已保存: {out_path}")
    return out_path
