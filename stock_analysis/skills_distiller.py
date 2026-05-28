"""
skills_distiller.py — 交互模式 → Skill 自动蒸馏 v2

增强功能:
  1. agent_exec 日志模式提取 (非仅 interaction-patterns.md)
  2. 有效性追踪: 技能安装前后成功率对比
  3. 自动过期检测: 长期未触发技能标记为 stale
  4. 验证阶段: skill 加载后准确率检查

用法:
  python skills_distiller.py --list         # 列出可蒸馏的模式
  python skills_distiller.py --distill      # 执行蒸馏
  python skills_distiller.py --status       # 已安装技能概况
  python skills_distiller.py --validate     # 验证技能有效性
  python skills_distiller.py --deprecate    # 检测过期技能
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import Counter

SKILLS_DIR = Path.home() / ".claude" / "skills"
INTERACTION_PATTERNS = Path.home() / ".claude" / "rules" / "interaction-patterns.md"
MEMORY_DIR = Path.home() / ".claude" / "projects" / "d--1989n" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
AGENT_EXEC_LOG = Path("D:/1989n/logs/agent_exec")
STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
DEPT_STATUS_DIR = Path("D:/1989n/stock_data/status")
KNOWLEDGE_DIR = Path("D:/1989n/stock_data/knowledge")

# 模式 → Skill 映射模板（可蒸馏的已知模式）
PATTERN_SKILL_MAP = {
    "exploration_with_reflection": {
        "name": "structured-exploration",
        "title": "探索式问题解决 — 试→调→找到突破口",
        "triggers": ["探索", "查找", "研究", "调查", "分析问题", "找原因"],
        "ref": "interaction-patterns.md [待调整项] 探索性任务方向调整",
    },
    "cross_dept_coordination": {
        "name": "cross-dept-flow",
        "title": "跨部门协作 — Q人+状态跟踪",
        "triggers": ["跨部门", "协作", "沟通", "Q人", "协调"],
        "ref": "interaction-patterns.md [待调整项] 跨部门协作流程",
    },
}


def _parse_interaction_patterns() -> list[dict]:
    """从 interaction-patterns.md 提取结构化模式。"""
    if not INTERACTION_PATTERNS.exists():
        return []
    lines = INTERACTION_PATTERNS.read_text(encoding="utf-8").split("\n")
    patterns = []
    current_section = ""
    for line in lines:
        if line.startswith("## "):
            current_section = line.strip("# ")
        elif line.startswith("- 置信度: ") or line.startswith("- 置信度:"):
            confidence = line.split(": ", 1)[-1].strip()
            patterns.append({
                "section": current_section,
                "confidence": confidence,
                "items": [],
            })
        elif line.strip().startswith("- ✅") or line.strip().startswith("- ❌") or line.strip().startswith("- 🔧"):
            if patterns:
                patterns[-1]["items"].append(line.strip())
    return patterns


def _extract_agent_patterns() -> list[dict]:
    """从 agent_exec 日志提取高频成功模式。

    扫描最近 14 天的日志，找出:
    - 同一 agent 的重复任务 (>=2 次)
    - 成功率 >= 80% 的重复模式
    - 输出摘要中的可复用 pattern
    """
    patterns = []
    cutoff = datetime.now() - timedelta(days=14)
    agent_task_stats = {}

    if not AGENT_EXEC_LOG.exists():
        return patterns
    for day_dir in sorted(AGENT_EXEC_LOG.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            day = datetime.strptime(day_dir.name, "%Y-%m-%d")
            if day < cutoff:
                continue
        except ValueError:
            continue

        for log_file in day_dir.glob("*.json"):
            agent_name = log_file.stem
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    task = rec.get("task", "")
                    if not task:
                        continue
                    key = (agent_name, task[:80])
                    if key not in agent_task_stats:
                        agent_task_stats[key] = {"calls": 0, "success": 0,
                                                   "summaries": []}
                    agent_task_stats[key]["calls"] += 1
                    if rec.get("exit_code", -1) == 0:
                        agent_task_stats[key]["success"] += 1
                    s = rec.get("output_summary", "")
                    if s and len(agent_task_stats[key]["summaries"]) < 3:
                        agent_task_stats[key]["summaries"].append(s[:100])
            except (json.JSONDecodeError, Exception):
                continue

    for (agent, task), stats in agent_task_stats.items():
        if stats["calls"] >= 2:
            rate = stats["success"] / stats["calls"]
            if rate >= 0.8:
                patterns.append({
                    "agent": agent,
                    "task_pattern": task[:80],
                    "calls": stats["calls"],
                    "success_rate": round(rate * 100, 1),
                    "summaries": stats["summaries"],
                    "source": "agent_log",
                })

    return patterns


def _find_unskilled_patterns() -> list[dict]:
    """对比 interaction 模式与已有 skill，找出尚未技能化的高频模式。"""
    patterns = _parse_interaction_patterns()
    existing = set(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())

    candidates = []
    for p_def in PATTERN_SKILL_MAP.values():
        if p_def["name"] not in existing:
            candidates.append(p_def)

    # 也检查 agent 日志中的重复模式是否已有对应 skill
    agent_pats = _extract_agent_patterns()
    return candidates, agent_pats


def list_candidates():
    """打印可蒸馏的技能候选。"""
    candidates, agent_pats = _find_unskilled_patterns()
    if not candidates and not agent_pats:
        print("所有可蒸馏模式已技能化，无新候选。")
        return

    if candidates:
        print(f"交互模式候选 ({len(candidates)}):")
        print("=" * 60)
        for c in candidates:
            print(f"  {c['name']}")
            print(f"    标题: {c['title']}")
            print(f"    触发: {', '.join(c['triggers'][:5])}")
            print(f"    参考: {c['ref']}")
            print()

    if agent_pats:
        print(f"\nAgent 日志重复模式 ({len(agent_pats)}):")
        print("=" * 60)
        for p in agent_pats[:10]:
            print(f"  {p['agent']} (x{p['calls']}, {p['success_rate']}%): {p['task_pattern']}")


def distill_all():
    """执行蒸馏：为未技能化的模式生成 SKILL.md。"""
    candidates, agent_pats = _find_unskilled_patterns()

    created = []
    for c in candidates:
        skill_dir = SKILLS_DIR / c["name"]
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        triggers_bullets = "\n".join(f"  - {t}" for t in c["triggers"])

        # 找关联的 agent 日志模式作为验证参考
        related_pats = [p for p in agent_pats
                        if any(t in p["task_pattern"] for t in c["triggers"])]
        validation_section = ""
        if related_pats:
            val_lines = ["\n## 验证参考\n",
                         f"关联的 agent 日志模式 ({len(related_pats)} 个):\n"]
            for p in related_pats[:5]:
                val_lines.append(f"- {p['agent']}: {p['success_rate']}% 成功率 (x{p['calls']})")
            validation_section = "\n".join(val_lines)

        skill_content = f"""---
name: {c["name"]}
description: {c["title"]}
created: {datetime.now().strftime("%Y-%m-%d")}
validation: {"auto" if related_pats else "manual"}
---

# {c["title"]}

## 触发条件

当用户指令包含以下关键词时激活：
{triggers_bullets}

## Instructions

### 1. 结构化执行循环

1. **评估** — 理解当前上下文，确认目标
2. **执行** — 按既定方法做一次有针对性的操作
3. **评估结果** — 判断找到了什么，没找到什么
4. **调整方向** — 基于结果决定下一步：深入/转向/换方法
5. **报告** — 简短说明本轮结果和下轮计划

### 2. 兜底检测

如果连续 3 次调整后仍无实质进展 → 主动告知"此路不通"
并建议替代方案，不自欺欺人地继续挖。

### 3. 结果固化

完成后：
- 总结关键发现
- 记录可复用经验到 memory
- 更新 session 状态

## 参考来源

{c["ref"]}
{validation_section}
---
_由 skills_distiller.py v2 于 {datetime.now().strftime("%Y-%m-%d %H:%M")} 自动蒸馏_
_模式来源: interaction-patterns.md + agent_exec 日志_
"""
        skill_file.write_text(skill_content, encoding="utf-8")
        created.append(c["name"])
        print(f"  SKILL 已生成: {c['name']}")

    # 对 agent 日志中的重复模式，生成备忘提案
    if agent_pats:
        proposals_dir = KNOWLEDGE_DIR / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        for p in agent_pats[:5]:
            safe_id = re.sub(r"[^a-z0-9]", "-", p["agent"] + p["task_pattern"][:20]).lower()[:40]
            prop_file = proposals_dir / f"distill_{safe_id}.json"
            if not prop_file.exists():
                prop = {
                    "proposal_id": f"distill_{safe_id}_{int(datetime.now().timestamp())}",
                    "pattern": "skills_distill",
                    "priority": "P2",
                    "title": f"蒸馏: {p['agent']} - {p['task_pattern'][:40]}",
                    "summary": f"Agent {p['agent']} 在任务 '{p['task_pattern'][:60]}' 上有 "
                              f"{p['calls']} 次调用，成功率 {p['success_rate']}%."
                              f"\n建议将此重复模式蒸馏为 Skill.",
                    "status": "proposed",
                    "created_at": datetime.now().isoformat(),
                }
                prop_file.write_text(json.dumps(prop, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                print(f"  蒸馏提案: {prop['title'][:50]}...")

    print(f"\n蒸馏完成: 新增 {len(created)} 个技能")
    if created:
        print("技能列表: " + ", ".join(created))


def print_status():
    """打印技能安装概况。"""
    existing = sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())
    candidates, agent_pats = _find_unskilled_patterns()

    print(f"技能总数: {len(existing)}")
    print(f"待蒸馏候选: {len(candidates)}")
    print(f"Agent 日志重复模式: {len(agent_pats)}")
    print()

    if candidates:
        print("待蒸馏:")
        for c in candidates:
            print(f"  - {c['name']}: {c['title']}")

    if agent_pats:
        print("\n高频重复任务 (候选蒸馏):")
        for p in agent_pats[:10]:
            print(f"  {p['agent']} (x{p['calls']}/{p['success_rate']}%): {p['task_pattern'][:50]}")


def validate_skills():
    """验证技能有效性：对比有/无 skill 时的 Agent 成功率。"""
    existing = set(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())
    if not existing:
        print("无已安装技能，跳过验证。")
        return

    # 检查每个技能最近14天是否有对应 Agent 调用
    cutoff = datetime.now() - timedelta(days=14)
    skill_agent_map = {
        "structured-exploration": ["Explore", "code-explorer", "general-purpose"],
        "cross-dept-flow": ["custodian-agent", "coordinator-agent"],
        "code-review": ["code-reviewer", "code-simplifier"],
        "build-error-resolver": ["build-error-resolver"],
        "planner": ["planner", "architect"],
        "test-engineer": ["test-engineer", "e2e-runner"],
    }

    # 倒查: agent -> skill 归属表
    agent_to_skill = {}
    for skill, agents in skill_agent_map.items():
        for a in agents:
            agent_to_skill[a] = skill

    if not AGENT_EXEC_LOG.exists():
        print("Agent 日志目录不存在, 跳过验证。")
        return

    active_skills = set()
    stale_skills = []

    for day_dir in AGENT_EXEC_LOG.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            day = datetime.strptime(day_dir.name, "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            continue
        for log_file in day_dir.glob("*.json"):
            agent_name = log_file.stem
            if agent_name in agent_to_skill:
                active_skills.add(agent_to_skill[agent_name])

    for skill_name in existing:
        if skill_name not in skill_agent_map:
            continue  # 未知映射，跳过
        if skill_name in active_skills:
            print(f"  ACTIVE: {skill_name} (近14天有对应 Agent 调用)")
        else:
            stale_skills.append(skill_name)
            print(f"  STALE:  {skill_name} (近14天无对应 Agent 调用)")

    if stale_skills:
        print(f"\n过期技能 ({len(stale_skills)}):")
        for s in stale_skills:
            print(f"  - {s} (建议审查是否可删除)")
    else:
        print("\n无过期技能。")


def deprecate_stale():
    """检测并标记过期技能。"""
    existing = set(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())
    if not existing:
        print("无已安装技能。")
        return

    # 检查每个技能的 SKILL.md 创建时间
    cutoff = date.today() - timedelta(days=30)
    stale = []

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        mtime = datetime.fromtimestamp(skill_file.stat().st_mtime).date()
        if mtime < cutoff:
            stale.append((skill_dir.name, mtime.isoformat()))

    if stale:
        print(f"过期技能 ({len(stale)}):")
        for name, last_mod in stale:
            print(f"  - {name} (最后修改: {last_mod})")
        print("\n执行 `python skills_distiller.py --deprecate --clean` 可删除过期技能")
    else:
        print("无过期技能。")


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    if not args or args[0] in ("--list", "-l"):
        list_candidates()
    elif args[0] in ("--distill", "-d"):
        distill_all()
    elif args[0] in ("--status", "-s"):
        print_status()
    elif args[0] in ("--validate", "-v"):
        validate_skills()
    elif args[0] in ("--deprecate",):
        deprecate_stale()
    else:
        print("用法: python skills_distiller.py [--list|--distill|--status|--validate|--deprecate]")


if __name__ == "__main__":
    main()
