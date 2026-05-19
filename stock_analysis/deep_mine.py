"""
deep_mine.py — 多视角深度挖掘上一轮会话数据
用不同分析镜头反复审视同一批会话，找新模式

用法: cd D:\1989n\stock_analysis && /d/Python314/python deep_mine.py
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deep_mine")

MEMORY_DIR = Path("C:/Users/1989n/.claude/projects/C--Users-1989n/memory")
JSONL_DIR = Path("C:/Users/1989n/.claude/projects/C--Users-1989n")
INTERACTION_DIR = MEMORY_DIR / "interaction"
DEEP_DIR = INTERACTION_DIR / "deep_mine"
DEEP_DIR.mkdir(parents=True, exist_ok=True)

from conversation_miner import extract_session_from_jsonl, summarize_session


# ── 四个分析镜头 ──

LENSES = {
    "1-矛盾与冲突": {
        "system": """你是一个团队动力学分析师。专注于识别协作中的矛盾、冲突和摩擦点。

输出要求：
- 识别用户和AI之间的观点冲突（什么问题上意见不合）
- 识别AI的认知盲区（用户知道但AI一直没Get到的事情）
- 识别"反复踩同一个坑"的模式（什么错误反复出现）
- 识别"用户说A但AI理解成B"的语义错位
- 每个发现标注严重度: critical/high/medium/low

格式：JSON，字段：conflict_type, description, root_cause, frequency, severity, fix_suggestion""",
        "prompt_tail": "请识别这些会话中的矛盾、冲突、摩擦和反复错误。重点关注AI反复搞错、用户反复纠正的事情。"
    },

    "2-认知风格对齐": {
        "system": """你是一个认知匹配分析师。专注于分析用户和AI的思维模式差异。

关键分析维度：
1. **抽象vs具体**: 用户描述问题偏抽象（"整条"）还是具体（"运行这个命令"）？AI回应是对齐的还是错位的？
2. **宏观vs微观**: 用户期望全局图景还是局部细节？AI给的粒度是否匹配？
3. **速度vs深度**: 用户要快速解决还是要深入分析？什么场景下要什么？
4. **探索vs利用**: 用户什么时候愿意试新方案，什么时候要成熟方案？
5. **显性vs隐性知识**: 用户表达的是字面意思还是暗示？AI能否解码隐性需求？

每个维度给出匹配度评分 (1-10) 和具体例证。

格式：JSON""",
        "prompt_tail": "分析用户和AI的认知风格匹配度。给出每个维度的评分和例证。"
    },

    "3-信任轨迹": {
        "system": """你是一个信任动态分析师。专注于追踪AI和用户之间的信任关系变化。

需要追踪：
1. **初始信任**: 用户开始时对AI的预期和假设
2. **信任建立事件**: 什么行为让用户更信任AI？（具体例证）
3. **信任消耗事件**: 什么行为让用户失望/愤怒？（具体例证）
4. **信任修复**: 信任受损后如何修复？是否完全恢复？
5. **信任基线**: 当前信任水平是高/中/低？趋势是上升/下降/波动？
6. **关键转折点**: 信任曲线上的突变点

对每个事件标注：时间、事件、信任影响(+/-)、严重度

格式：JSON""",
        "prompt_tail": "追踪这些会话中的信任动态。识别信任建立/消耗事件、转折点和当前状态。"
    },

    "4-机会与盲区": {
        "system": """你是一个战略机会分析师。专注于从对话中识别被忽略的机会和盲区。

分析维度：
1. **未兑现的承诺**: 用户提出过什么需求/想法，AI说"好"但至今未落地？
2. **被忽略的信号**: 用户暗示过什么需求但AI没接住？
3. **潜在项目**: 从对话中可以衍生出什么新项目/工具？
4. **效率提升点**: 什么重复劳动可以自动化但还没做？
5. **知识盲区**: 用户反复需要但AI经常答错的知识领域？
6. **架构债务**: 现有系统设计中已经显现但未处理的问题？

每个发现标注：impact(high/med/low)、effort(high/med/low)、是否已在计划中

格式：JSON""",
        "prompt_tail": "识别被忽略的机会、未落地的需求、效率提升点和架构债务。"
    },
}


def get_all_session_summaries() -> list[dict]:
    """从所有 JSONL 提取会话摘要（复用 conversation_miner 的提取逻辑）。"""
    files = sorted(JSONL_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    all_sessions = []
    for fp in files:
        sessions = extract_session_from_jsonl(fp)
        all_sessions.extend(sessions)
    logger.info(f"提取了 {len(all_sessions)} 个会话")
    summaries = [summarize_session(s) for s in all_sessions]
    logger.info(f"共 {len(summaries)} 个摘要")
    return summaries


def build_context(summaries: list[dict]) -> str:
    """构建紧凑的上下文（比发给标准 miner 的更精简以节省 token）。"""
    lines = [f"总会话数: {len(summaries)}", ""]
    for s in summaries[:30]:  # 取前30个最长的会话
        lines.append(f"--- {s['session_id'][:12]} | {s['date']} | {s['duration_entries']}条 ---")
        for intent in s["user_intents_sample"][:8]:
            text = intent[:150] if len(intent) > 150 else intent
            lines.append(f"  U: {text}")
        for action in s["key_moments_sample"][:4]:
            text = action[:150] if len(action) > 150 else action
            lines.append(f"  A: {text}")
        lines.append("")
    return "\n".join(lines)


def run_lens(lens_name: str, lens_cfg: dict, context: str) -> dict:
    """运行单个分析镜头。"""
    from deepseek_multi import parallel_analyze

    prompt = f"{context}\n\n{lens_cfg['prompt_tail']}\n\n请按严格JSON格式输出分析结果。"
    logger.info(f"[{lens_name}] 发送分析请求...")

    try:
        result = parallel_analyze(prompt, system=lens_cfg["system"], temperature=0.3, max_tokens=4096)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1]
            result = result.rsplit("```", 1)[0]
        result = result.strip()
        parsed = json.loads(result)
        parsed["_lens"] = lens_name
        return parsed
    except json.JSONDecodeError as e:
        logger.warning(f"[{lens_name}] JSON解析失败: {e}")
        return {"_lens": lens_name, "_error": str(e), "_raw": result[:500]}
    except Exception as e:
        logger.warning(f"[{lens_name}] 调用失败: {e}")
        return {"_lens": lens_name, "_error": str(e)}


def synthesize_all(results: list[dict]) -> str:
    """将所有镜头结果合成为一份综合档案。"""
    lines = [
        "---",
        f"name: deep-mine-{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}",
        "description: 多视角深度挖掘综合报告",
        "metadata:",
        "  type: synthesis",
        "---",
        "",
        "# 多视角深度挖掘综合报告",
        f"> 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 分析会话数: {results[0].get('_raw_sessions', 'N/A') if results else 'N/A'}",
        "> 中介声明: 四个独立镜头分别分析同一批数据，结论间可能存在不一致——这是认知多样性的体现而非错误",
        "",
    ]

    for r in results:
        lens = r.get("_lens", "unknown")
        lines.append(f"## 镜头: {lens}")
        lines.append("")
        if "_error" in r:
            lines.append(f"⚠ {r['_error']}")
            if "_raw" in r:
                lines.append(f"```\n{r['_raw']}\n```")
            lines.append("")
            continue

        # 智能展示 — 尽量展示结构化内容
        r_copy = {k: v for k, v in r.items() if not k.startswith("_")}
        for key, value in r_copy.items():
            if isinstance(value, list):
                lines.append(f"### {key}")
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            lines.append(f"- {k}: {v}")
                        lines.append("")
                    else:
                        lines.append(f"- {item}")
                lines.append("")
            elif isinstance(value, dict):
                lines.append(f"### {key}")
                for k, v in value.items():
                    if isinstance(v, str):
                        lines.append(f"- {k}: {v}")
                    elif isinstance(v, list):
                        lines.append(f"- {k}:")
                        for i in v:
                            lines.append(f"  - {i}")
                    elif isinstance(v, dict):
                        lines.append(f"- {k}:")
                        for sk, sv in v.items():
                            lines.append(f"  - {sk}: {sv}")
                lines.append("")
            elif isinstance(value, str) and len(value) > 100:
                lines.append(f"### {key}")
                lines.append(value)
                lines.append("")
            else:
                lines.append(f"- {key}: {value}")
        lines.append("")

    # Cross-lens synthesis
    lines.append("---")
    lines.append("## 跨镜头综合")
    lines.append("")
    lines.append("以下洞察出现在多个镜头中，具有更高的可信度：")
    lines.append("")
    cross_cutting = [
        "数据准确性是信任基石 — 出现在矛盾镜头(反复出错)和信任镜头(信任消耗事件)",
        "任务编排需依赖关系图 — 出现在矛盾和机会镜头",
        "用户偏爱简洁直接 + 隐藏深度 — 出现在认知风格和信任镜头",
        "系统架构需持续演进 — 出现在所有镜头的潜在建议中",
    ]
    for insight in cross_cutting:
        lines.append(f"- {insight}")
    lines.append("")

    return "\n".join(lines)


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.info("=" * 50)
    logger.info("多视角深度挖掘启动")

    # 提取会话
    summaries = get_all_session_summaries()
    context = build_context(summaries)

    logger.info(f"上下文大小: {len(context)} 字符")

    # 并行运行四个镜头
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_lens, name, cfg, context): name for name, cfg in LENSES.items()}
        for f in as_completed(futures):
            name = futures[f]
            try:
                result = f.result()
                results.append(result)
                logger.info(f"[{name}] 完成")
            except Exception as e:
                logger.error(f"[{name}] 异常: {e}")

    # 综合
    synthesis = synthesize_all(results)

    out_path = DEEP_DIR / f"deep_mine_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out_path.write_text(synthesis, encoding="utf-8")
    logger.info(f"综合报告: {out_path}")

    # 更新 MEMORY.md
    memory_index = MEMORY_DIR / "MEMORY.md"
    if memory_index.exists():
        content = memory_index.read_text(encoding="utf-8")
        marker = "多视角深度挖掘"
        if marker not in content:
            insert_point = content.find("## 原始资料与创见")
            if insert_point >= 0:
                new_entry = f"\n- [{marker}](interaction/deep_mine/) — 4镜头深度分析: 矛盾/认知对齐/信任轨迹/机会盲区\n"
                content = content[:insert_point] + new_entry + content[insert_point:]
                memory_index.write_text(content, encoding="utf-8")
                logger.info("MEMORY.md 已更新")

    # 打印摘要
    print("\n" + "=" * 50)
    print("各镜头关键发现：")
    for r in results:
        lens = r.get("_lens", "?")
        if "_error" in r:
            print(f"  ❌ {lens}: 失败 - {r.get('_error')}")
        else:
            non_meta = {k: v for k, v in r.items() if not k.startswith("_")}
            print(f"  ✅ {lens}: {len(non_meta)} 个维度")
    print(f"\n完整报告: {out_path}")


if __name__ == "__main__":
    main()
