"""
daily_compress_agent.py — DeepSeek 驱动的每日复盘压缩

15:37 触发，读全天数据 → 压缩为5段认知摘要 → 写入 daily/ + 飞书

待实现：完整的复盘数据采集
"""
import logging, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cognitive_engine import load_context, deepseek_reason, send_output, save_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
logger = logging.getLogger("daily_compress_agent")
CST = timezone(timedelta(hours=8))

def main():
    logger.info("Daily Compress Agent starting...")
    # TODO: 读全天数据（行情/持仓/交易/新闻/情绪）
    context = load_context([
        "knowledge/stocks/volume-price-cycle.md",
        "knowledge/stocks/trading-discipline.md",
    ])
    prompt = f"生成今日认知压缩摘要（{datetime.now(CST).strftime('%Y-%m-%d')}）"
    result = deepseek_reason("review", prompt, system_prompt=context)
    save_output("daily_compress", result)
    send_output("每日复盘", result, route="main")
    logger.info("完成")

if __name__ == "__main__":
    main()
