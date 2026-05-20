"""
conversation_miner.py — SEL Digest 引擎：对话挖掘 → 模式提取 → memory固化

架构：
  scan() → extract_session() → analyze_session() → synthesize() → persist()

四类信号提取:
  1. 任务模式     — 用户什么时间/场景下达什么任务，偏好什么粒度
  2. 反馈信号     — 什么产出被拒收/通过/修改，根因是什么
  3. 决策脉络     — 从问题到方案的关键路径，用户否决/接受什么
  4. 隐性偏好     — 用户没明说但反复体现的协作风格

中介声明 (U4)：本引擎的分析基于 JSONL 对话文本的模式匹配和 LLM 推断，
  不反映用户的完整意图或未表达的需求。所有推断标注置信度。

用法：
  python conversation_miner.py               # 增量运行（只处理新会话）
  python conversation_miner.py --full         # 全量回溯
  python conversation_miner.py --report       # 只看上次报告
"""

import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── 路径配置 ──

BASE_DATA = Path("D:/1989n/stock_data/interaction")
INTERACTION_DIR = BASE_DATA
SESSIONS_DIR = BASE_DATA / "sessions"
DAILY_DIR = BASE_DATA / "daily"
DEEP_MINE_DIR = BASE_DATA / "deep_mine"
STATE_FILE = BASE_DATA / ".miner_state.json"

# JSONL 读取源（C 盘 Claude Code 项目目录，只读不写）
C_JSONL_DIRS = [
    Path("C:/Users/1989n/.claude/projects/d--1989n"),
    Path("C:/Users/1989n/.claude/projects/C--Users-1989n"),
]

STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
sys.path.insert(0, str(STOCK_ANALYSIS))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("conversation_miner")

# ── 确保目录 ──
MEMORY_INDEX = Path("C:/Users/1989n/.claude/projects/d--1989n/memory/MEMORY.md")

for d in [INTERACTION_DIR, SESSIONS_DIR, DAILY_DIR, DEEP_MINE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 阶段1: 扫描 — 找未处理的JSONL
# ════════════════════════════════════════════════════════════════

def load_state() -> dict:
    """加载处理状态：记录每个文件已处理到的行号。"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"file_offsets": {}, "last_run": None, "total_sessions_processed": 0}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_jsonl_files(full_scan: bool = False) -> list[tuple[Path, int]]:
    """遍历 C_JSONL_DIRS，返回 (文件路径, 起始行号) 列表。

    state key 用 {dir_name}/{file_name} 避免两个目录文件名冲突。
    """
    state = load_state()
    offsets = state.get("file_offsets", {})

    to_process = []
    for src_dir in C_JSONL_DIRS:
        if not src_dir.exists():
            continue
        for fp in sorted(src_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            key = f"{src_dir.name}/{fp.name}"
            current_lines = sum(1 for _ in fp.open(encoding="utf-8", errors="replace"))
            # 兼容旧 state key（无目录前缀的 RAW_DIR 时期）
            last_offset = 0 if full_scan else offsets.get(key, offsets.get(fp.name, 0))

            if current_lines > last_offset:
                to_process.append((fp, last_offset))
                offsets[key] = current_lines

    state["file_offsets"] = offsets
    save_state(state)
    return to_process


# ════════════════════════════════════════════════════════════════
# 阶段2: 提取 — 从JSONL提取紧凑的会话摘要
# ════════════════════════════════════════════════════════════════

def extract_user_intent(msg: dict) -> str:
    """从 user 消息提取意图。"""
    raw = msg.get("message")
    if raw is None:
        return ""
    if isinstance(raw, str):
        content = raw
    elif isinstance(raw, dict):
        content = raw.get("content", "")
    elif isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict):
                texts.append(block.get("text", "") or block.get("content", ""))
            elif isinstance(block, str):
                texts.append(block)
        content = " ".join(texts)
    else:
        content = str(raw)

    # content 可能是列表（嵌套内容块）
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        content = " ".join(texts)

    if not isinstance(content, str):
        content = str(content)
    if "<local-command-caveat>" in content:
        return ""
    content = content.strip()
    if not content or len(content) < 3:
        return ""
    return content


def extract_assistant_action(msg: dict) -> str:
    """从 assistant 消息提取关键动作（工具调用 + 回复摘要）。"""
    raw = msg.get("message", {})
    if isinstance(raw, dict):
        content_blocks = raw.get("content", [])
    elif isinstance(raw, str):
        content_blocks = [{"type": "text", "text": raw}]
    else:
        return ""

    actions = []
    for block in content_blocks if isinstance(content_blocks, list) else [content_blocks]:
        t = block.get("type", "")
        if t == "tool_use":
            name = block.get("name", "")
            inp = block.get("input", {})
            if isinstance(inp, dict):
                inp_str = json.dumps(inp, ensure_ascii=False)[:150]
            else:
                inp_str = str(inp)[:150]
            actions.append(f"[tool:{name}] {inp_str}")
        elif t == "text":
            text = block.get("text", "")[:200]
            if text.strip():
                actions.append(text[:200])
    return " | ".join(actions[:5])


def extract_session_from_jsonl(fp: Path, start_line: int = 0) -> list[dict]:
    """从JSONL文件提取完整会话列表。

    返回:
        [{"session_id", "entries": [{"role","time","content","actions"}, ...]}, ...]
    """
    sessions: dict[str, list] = defaultdict(list)

    with fp.open(encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f):
            if line_no < start_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = record.get("type", "")
            ts = record.get("timestamp", "")
            session_id = record.get("sessionId", fp.stem)

            if msg_type == "user":
                intent = extract_user_intent(record)
                if intent:
                    sessions[session_id].append({
                        "role": "user",
                        "time": ts,
                        "content": intent,
                    })
            elif msg_type == "assistant":
                actions = extract_assistant_action(record)
                if actions:
                    sessions[session_id].append({
                        "role": "assistant",
                        "time": ts,
                        "content": actions,
                    })
            elif msg_type == "queue-operation":
                content = record.get("content", "")
                if content:
                    sessions[session_id].append({
                        "role": "system",
                        "time": ts,
                        "content": f"[scheduled] {content}",
                    })

    # 按时间排序，合并成紧凑摘要
    result = []
    for sid, entries in sessions.items():
        entries.sort(key=lambda e: e.get("time", ""))
        # 截取前60条交互（避免超长会话撑爆token）
        if len(entries) > 60:
            # 保留开头和结尾
            entries = entries[:30] + [{"role": "...", "time": "", "content": f"... ({len(entries)-60} 条省略)"}] + entries[-30:]
        result.append({
            "session_id": sid,
            "date": _session_date(entries),
            "entry_count": len(entries),
            "entries": entries,
        })

    return result


def _session_date(entries: list) -> str:
    """从会话条目推断日期。"""
    for e in entries:
        ts = e.get("time", "")
        if ts:
            try:
                return ts[:10]
            except (IndexError, ValueError):
                pass
    return "unknown"


def summarize_session(session: dict) -> dict:
    """将原始会话压缩为结构化摘要，用于 DeepSeek 分析。

    输出:
        {"session_id", "date", "user_intents": [], "key_moments": []}
    """
    intents = []
    key_moments = []

    for e in session["entries"]:
        if e["role"] == "user":
            intents.append(e["content"])
        elif e["role"] == "assistant":
            content = e["content"]
            if "[tool:" in content:
                key_moments.append(content)

    return {
        "session_id": session["session_id"],
        "date": session["date"],
        "duration_entries": session["entry_count"],
        "user_message_count": len(intents),
        "user_intents_sample": intents[:15],  # 最多15条
        "key_moments_sample": key_moments[:10],
    }


# ════════════════════════════════════════════════════════════════
# 阶段3: 分析 — DeepSeek 跨会话模式提取
# ════════════════════════════════════════════════════════════════

ANALYSIS_SYSTEM_PROMPT = """你是一个交互分析专家。你的任务是从对话记录中提取协作模式和隐性知识。

**中介声明 (U4)**：你的分析基于有限的文本记录，无法感知用户的语气、情绪或未表达的意图。
所有推断必须标注置信度: [high] / [medium] / [low]。

## 四类信号提取要求

### 1. 任务模式 [high/medium/low]
用户通常在什么时间、什么上下文下发起什么类型的任务？任务描述的粒度如何？
- 时间模式：几点、周几、盘前/盘中/盘后/睡前
- 任务类型：数据修复 / 架构设计 / 知识管理 / 策略分析
- 粒度偏好：模糊指令 vs 精确指令
- 重复模式：哪些任务反复出现

### 2. 反馈信号 [high/medium/low]
用户对什么类型的产出接受/拒绝/要求修改？根因是什么？
- 接受模式：什么样的格式/深度/角度被接受
- 拒绝模式：什么样的产出被拒，拒因是什么（太浅/方向错/缺数据）
- 修改模式：用户要求改什么，改的方向是什么
- 沉默信号：什么情况下用户不回复（可能是默认接受或放弃）

### 3. 决策脉络 [medium/low]
从问题到方案的关键选择点。
- 用户否决了什么方案？为什么？
- 用户接受了什么方案？为什么？
- 什么因素驱动了决策转向？

### 4. 隐性偏好 [medium/low]
用户没有明说但反复体现的协作风格。
- 沟通风格：简洁/详细/结构化/自由
- 期望水平：什么算"够好" vs "交差"
- 信任信号：什么情况下用户直接接受，什么情况下要求验证
"""


def build_analysis_prompt(session_summaries: list[dict]) -> str:
    """构建跨会话分析 prompt。"""
    context = f"分析时段: 共 {len(session_summaries)} 个会话\n"
    context += f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    for s in session_summaries:
        context += f"--- 会话 {s['session_id'][:12]} | {s['date']} | {s['duration_entries']}条交互 ---\n"
        context += f"用户消息({s['user_message_count']}条):\n"
        for intent in s["user_intents_sample"]:
            # 截断过长消息
            if len(intent) > 200:
                intent = intent[:200] + "..."
            context += f"  U: {intent}\n"
        context += f"关键动作:\n"
        for action in s["key_moments_sample"]:
            if len(action) > 200:
                action = action[:200] + "..."
            context += f"  A: {action}\n"
        context += "\n"

    context += """
请按以下 JSON 格式输出分析结果（严格 JSON，不要 markdown 代码块）：
{
    "mediation": "此分析基于有限的文本记录，不反映用户的完整意图",
    "task_patterns": {
        "time_distribution": "描述",
        "common_task_types": ["type1", "type2"],
        "granularity_preference": "描述",
        "recurring_tasks": ["task1", "task2"],
        "confidence": "high/medium/low"
    },
    "feedback_signals": {
        "accepted_patterns": ["pattern1"],
        "rejected_patterns": [{"pattern": "描述", "likely_reason": "根因"}],
        "modification_requests": [{"request": "描述", "direction": "方向"}],
        "confidence": "high/medium/low"
    },
    "decision_patterns": {
        "key_turning_points": [{"problem": "问题", "rejected": "被否的方案", "accepted": "接受的方案", "driver": "决策驱动力"}],
        "confidence": "medium/low"
    },
    "latent_preferences": {
        "communication_style": "描述",
        "quality_threshold": "描述",
        "trust_signals": ["signal1"],
        "confidence": "medium/low"
    },
    "action_items": [
        {"what": "应该改变什么", "why": "为什么", "priority": "high/medium/low"}
    ]
}
"""
    return context


def analyze_sessions(session_summaries: list[dict]) -> dict:
    """用 DeepSeek 进行跨会话分析。"""
    if not session_summaries:
        return {"mediation": "无新会话可分析", "patterns": {}}

    # 引入 DeepSeek 通道
    try:
        from deepseek_multi import parallel_analyze
    except ImportError:
        logger.warning("deepseek_multi 不可用，使用 fallback 本地分析")
        return _fallback_analyze(session_summaries)

    prompt = build_analysis_prompt(session_summaries)
    logger.info(f"发送 {len(session_summaries)} 个会话到 DeepSeek 分析...")

    try:
        result = parallel_analyze(prompt, system=ANALYSIS_SYSTEM_PROMPT, temperature=0.2, max_tokens=4096)
        # 尝试解析 JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1]
            result = result.rsplit("```", 1)[0]
        result = result.strip()
        parsed = json.loads(result)
        parsed["_raw_sessions"] = len(session_summaries)
        return parsed
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"DeepSeek 返回解析失败: {e}，回退本地分析")
        return _fallback_analyze(session_summaries)


def _fallback_analyze(session_summaries: list[dict]) -> dict:
    """本地 fallback：基础统计 + 简单模式识别。"""
    intents_all = []
    for s in session_summaries:
        intents_all.extend(s["user_intents_sample"])

    # 关键词统计
    task_keywords = {
        "数据修复/回补": ["修复", "恢复", "回补", "补数据", "挂了", "404", "死了"],
        "架构设计": ["架构", "方案", "设计", "重构", "管道", "pipeline"],
        "知识管理": ["记忆", "memory", "保存", "存储", "知识库"],
        "策略分析": ["分析", "判断", "评估", "怎么看", "研究"],
        "问题诊断": ["为什么", "什么原因", "排查", "检查", "问题"],
    }

    task_counts = defaultdict(int)
    for intent in intents_all:
        for category, keywords in task_keywords.items():
            if any(k in intent for k in keywords):
                task_counts[category] += 1

    # 反馈信号
    reject_keywords = ["不行", "很差", "不好", "拒绝", "不是", "没", "不要", "别"]
    accept_keywords = ["好", "行", "ok", "可以", "不错", "是的", "对的", "同意"]

    reject_count = sum(1 for i in intents_all if any(k in i for k in reject_keywords))
    accept_count = sum(1 for i in intents_all if any(k in i for k in accept_keywords))

    return {
        "mediation": "Fallback 本地分析 — 仅基于关键词统计，置信度低",
        "task_patterns": {
            "time_distribution": "fallback: 无时间分析",
            "common_task_types": sorted(task_counts.keys(), key=lambda k: task_counts[k], reverse=True)[:5],
            "granularity_preference": "fallback: 需 DeepSeek 分析",
            "recurring_tasks": [k for k, v in task_counts.items() if v >= 2],
            "confidence": "low",
        },
        "feedback_signals": {
            "accepted_patterns": [f"关键词匹配: 接受信号 {accept_count} 次"],
            "rejected_patterns": [{"pattern": "关键词匹配", "likely_reason": f"拒绝信号 {reject_count} 次"}],
            "modification_requests": [],
            "confidence": "low",
        },
        "decision_patterns": {"key_turning_points": [], "confidence": "low"},
        "latent_preferences": {
            "communication_style": "fallback: 需 DeepSeek 分析",
            "quality_threshold": "fallback: 需 DeepSeek 分析",
            "trust_signals": [],
            "confidence": "low",
        },
        "action_items": [{"what": "配置 DeepSeek API 以获得深度分析", "why": "当前使用 fallback 模式，只有关键词统计", "priority": "high"}],
        "_raw_sessions": len(session_summaries),
        "_is_fallback": True,
    }


# ════════════════════════════════════════════════════════════════
# 阶段4: 固化 — 写回 memory/ + 更新索引
# ════════════════════════════════════════════════════════════════

def persist_interaction_patterns(analysis: dict):
    """将分析结果写入 memory/interaction/interaction-patterns.md。"""
    today = datetime.now().strftime("%Y-%m-%d")

    lines = ["---",
             f"name: interaction-patterns",
             f"description: 用户交互模式分析 — 持续累积 (更新 {today})",
             f"metadata:",
             f"  type: user",
             f"---",
             "",
             f"# 交互模式累积档案",
             "",
             f"> 最后更新: {today}",
             f"> 中介声明: 基于 JSONL 对话文本的模式分析，不反映用户未表达的意图",
             "",
             ]

    if analysis.get("_is_fallback"):
        lines.append("> ⚠ 当前为 Fallback 模式（DeepSeek API 不可用），仅关键词统计")
        lines.append("")

    # 任务模式
    tp = analysis.get("task_patterns", {})
    lines.append("## 任务模式")
    lines.append(f"- 置信度: {tp.get('confidence', 'N/A')}")
    lines.append(f"- 时间分布: {tp.get('time_distribution', 'N/A')}")
    lines.append(f"- 常见任务类型: {', '.join(tp.get('common_task_types', ['N/A']))}")
    lines.append(f"- 粒度偏好: {tp.get('granularity_preference', 'N/A')}")
    if tp.get("recurring_tasks"):
        lines.append(f"- 重复任务: {', '.join(tp['recurring_tasks'])}")
    lines.append("")

    # 反馈信号
    fs = analysis.get("feedback_signals", {})
    lines.append("## 反馈信号")
    lines.append(f"- 置信度: {fs.get('confidence', 'N/A')}")
    for p in fs.get("accepted_patterns", []):
        lines.append(f"- ✅ 接受: {p}")
    for p in fs.get("rejected_patterns", []):
        lines.append(f"- ❌ 拒绝: {p.get('pattern', p)} (根因: {p.get('likely_reason', 'N/A')})")
    for p in fs.get("modification_requests", []):
        lines.append(f"- 🔧 修改: {p.get('request', p)} → {p.get('direction', 'N/A')}")
    lines.append("")

    # 决策脉络
    dp = analysis.get("decision_patterns", {})
    lines.append("## 决策脉络")
    lines.append(f"- 置信度: {dp.get('confidence', 'N/A')}")
    for tp_pt in dp.get("key_turning_points", []):
        lines.append(f"- 问题: {tp_pt.get('problem', 'N/A')}")
        lines.append(f"  ✗ 被否: {tp_pt.get('rejected', 'N/A')}")
        lines.append(f"  ✓ 接受: {tp_pt.get('accepted', 'N/A')}")
        lines.append(f"  驱动力: {tp_pt.get('driver', 'N/A')}")
    lines.append("")

    # 隐性偏好
    lp = analysis.get("latent_preferences", {})
    lines.append("## 隐性偏好")
    lines.append(f"- 置信度: {lp.get('confidence', 'N/A')}")
    lines.append(f"- 沟通风格: {lp.get('communication_style', 'N/A')}")
    lines.append(f"- 质量标准: {lp.get('quality_threshold', 'N/A')}")
    for s in lp.get("trust_signals", []):
        lines.append(f"- 信任信号: {s}")
    lines.append("")

    # 行动项
    lines.append("## 待调整项")
    for item in analysis.get("action_items", []):
        pri = item.get("priority", "medium")
        lines.append(f"- [{pri.upper()}] {item.get('what', '')} (原因: {item.get('why', '')})")

    out_path = INTERACTION_DIR / "interaction-patterns.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"交互模式写入: {out_path}")


def persist_daily_report(analysis: dict):
    """写日报到 memory/interaction/daily/YYYY-MM-DD.md。"""
    today = datetime.now().strftime("%Y-%m-%d")
    state = load_state()

    lines = [f"# 交互挖掘日报 | {today}",
             f"",
             f"处理会话数: {analysis.get('_raw_sessions', 0)}",
             f"累计处理: {state.get('total_sessions_processed', 0)}",
             f"分析模式: {'DeepSeek' if not analysis.get('_is_fallback') else 'Fallback(关键词)'}",
             f"",
             ]

    # 新洞察
    if analysis.get("action_items"):
        lines.append("## 新洞察")
        for item in analysis["action_items"]:
            lines.append(f"- [{item.get('priority', 'med').upper()}] {item.get('what', '')}")

    # 更新 feedback/ 的建议
    if analysis.get("feedback_signals", {}).get("rejected_patterns"):
        lines.append("## 建议更新 feedback 规则")
        for rp in analysis["feedback_signals"]["rejected_patterns"]:
            lines.append(f"- 用户拒绝了: {rp.get('pattern', 'N/A')}")
            lines.append(f"  → 根因: {rp.get('likely_reason', 'N/A')}")

    out_path = DAILY_DIR / f"{today}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"日报写入: {out_path}")


def update_memory_index():
    """在 MEMORY.md 写入指针（实际数据在 D 盘）。"""
    if not MEMORY_INDEX.exists():
        return

    # 写指针文件到 memory 目录（MEMORY.md 只认同级文件）
    pointer_path = MEMORY_INDEX.parent / "interaction-patterns.md"
    pointer_path.write_text(
        "---\n"
        "name: interaction-patterns\n"
        "description: 交互模式档案（数据位于 D 盘）\n"
        "metadata:\n"
        "  type: user\n"
        "---\n"
        "\n"
        "# 交互模式档案\n\n"
        "实际数据文件: `D:/1989n/stock_data/interaction/interaction-patterns.md`\n"
        "每日日报: `D:/1989n/stock_data/interaction/daily/`\n"
        "原始会话: `D:/1989n/stock_data/interaction/raw/`\n",
        encoding="utf-8",
    )

    content = MEMORY_INDEX.read_text(encoding="utf-8")
    marker = "- [交互模式档案](interaction-patterns.md)"

    if marker not in content:
        content += f"\n{marker} — 对话挖掘输出，数据在 D 盘\n"
        MEMORY_INDEX.write_text(content, encoding="utf-8")
        logger.info("MEMORY.md 已添加交互模式指针")


# ════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════

def validate_jsonl_dir():
    """检查 C_JSONL_DIRS 中至少一个有 .jsonl 文件。"""
    for src_dir in C_JSONL_DIRS:
        if src_dir.exists() and list(src_dir.glob("*.jsonl")):
            return True
    logger.error(f"C_JSONL_DIRS 均无 .jsonl 文件: {[str(d) for d in C_JSONL_DIRS]}")
    return False


def main():
    import sys

    full_scan = "--full" in sys.argv
    report_only = "--report" in sys.argv

    if report_only:
        state = load_state()
        date_str = state.get("last_run", "N/A")
        print(f"上次运行: {date_str}")
        print(f"累计处理会话: {state.get('total_sessions_processed', 0)}")

        report_file = DAILY_DIR / f"{date_str[:10]}.md" if date_str != "N/A" else None
        if report_file and report_file.exists():
            print(report_file.read_text(encoding="utf-8"))
        return

    if not validate_jsonl_dir():
        return

    # 阶段1: 扫描
    logger.info("阶段1: 扫描 JSONL 文件...")
    to_process = scan_jsonl_files(full_scan=full_scan)
    if not to_process:
        logger.info("无新会话需处理")
        return

    logger.info(f"发现 {len(to_process)} 个文件需处理")

    # 阶段2: 提取会话
    logger.info("阶段2: 提取会话摘要...")
    all_sessions = []
    for fp, offset in to_process:
        sessions = extract_session_from_jsonl(fp, start_line=offset)
        all_sessions.extend(sessions)
        logger.info(f"  {fp.name}: {len(sessions)} 个会话")

    if not all_sessions:
        logger.info("无可分析的会话")
        return

    # 压缩为摘要
    summaries = [summarize_session(s) for s in all_sessions]
    logger.info(f"共 {len(summaries)} 个会话摘要")

    # 阶段3: 分析
    logger.info("阶段3: DeepSeek 跨会话分析...")
    analysis = analyze_sessions(summaries)

    # 阶段4: 固化
    logger.info("阶段4: 写入 memory...")
    persist_interaction_patterns(analysis)
    persist_daily_report(analysis)

    # 更新状态
    state = load_state()
    state["last_run"] = datetime.now().isoformat()
    state["total_sessions_processed"] = state.get("total_sessions_processed", 0) + len(all_sessions)
    save_state(state)

    # 更新 MEMORY.md 索引
    update_memory_index()

    logger.info(f"完成: {len(all_sessions)} 个会话 → memory/interaction/")


if __name__ == "__main__":
    import sys
    main()
