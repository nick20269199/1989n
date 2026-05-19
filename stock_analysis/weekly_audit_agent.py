"""
weekly_audit_agent.py — DeepSeek 驱动的周度认知审计

周六 10:07 触发，读本周5条压缩摘要 → 模式识别 + 规则审计 + 三轨评分
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cognitive_engine import load_context, deepseek_reason, send_output, save_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
logger = logging.getLogger("weekly_audit_agent")

def main():
    logger.info("Weekly Audit Agent starting...")
    # TODO: 读本周 daily/*.md 和 _lint_history.json
    context = load_context(["project/cognitive-flywheel.md"])
    prompt = "读本周每日复盘摘要，做模式识别 + 规则有效性审计 + 三轨健康度评分"
    result = deepseek_reason("research", prompt, system_prompt=context)
    save_output("weekly_audit", result)
    send_output("周度审计", result, route="main")
    logger.info("完成")

if __name__ == "__main__":
    main()
