"""
skills_distiller.py — 交互模式 → Skill 自动蒸馏

从 interaction-patterns.md 提取高频重复模式，
自动生成或更新 .claude/skills/<name>/SKILL.md。

用法:
  python skills_distiller.py --list         # 列出可蒸馏的模式
  python skills_distiller.py --distill      # 执行蒸馏
  python skills_distiller.py --status       # 已安装技能概况
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

SKILLS_DIR = Path.home() / ".claude" / "skills"
INTERACTION_PATTERNS = Path.home() / ".claude" / "rules" / "interaction-patterns.md"
MEMORY_DIR = Path.home() / ".claude" / "projects" / "d--1989n" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"

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


def _find_unskilled_patterns() -> list[dict]:
    """对比 interaction 模式与已有 skill，找出尚未技能化的高频模式。"""
    patterns = _parse_interaction_patterns()
    existing = set(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())

    candidates = []
    for p_def in PATTERN_SKILL_MAP.values():
        if p_def["name"] not in existing:
            candidates.append(p_def)

    return candidates


def list_candidates():
    """打印可蒸馏的技能候选。"""
    candidates = _find_unskilled_patterns()
    if not candidates:
        print("所有可蒸馏模式已技能化，无新候选。")
        return
    print(f"可蒸馏的技能候选 ({len(candidates)}):")
    print("=" * 60)
    for c in candidates:
        print(f"  {c['name']}")
        print(f"    标题: {c['title']}")
        print(f"    触发: {', '.join(c['triggers'][:5])}")
        print(f"    参考: {c['ref']}")
        print()


def distill_all():
    """执行蒸馏：为未技能化的模式生成 SKILL.md。"""
    candidates = _find_unskilled_patterns()
    if not candidates:
        print("无新技能需要生成。")
        return

    created = []
    for c in candidates:
        skill_dir = SKILLS_DIR / c["name"]
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        triggers_bullets = "\n".join(f"  - {t}" for t in c["triggers"])
        skill_content = f"""---
name: {c["name"]}
description: {c["title"]}
---

# {c["title"]}

## 触发条件

当用户指令包含以下关键词时激活：
{triggers_bullets}

## Instructions

### 1. 结构化探索循环

每轮探索后必须做方向调整：

1. **执行探索** — 按当前方向做一次有针对性的搜索/分析
2. **评估结果** — 判断找到了什么，没找到什么
3. **调整方向** — 基于结果决定下一步：深入/转向/换方法
4. **报告进度** — 简短说明本轮发现了什么，下轮打算怎么找
5. **重复** — 直到找到答案或方向彻底证明不通

### 2. 死路检测

如果连续 3 次调整后仍无实质进展 → 主动告知用户"此路不通"
并建议替代方案，不自欺欺人地继续挖。

### 3. 结果固化

找到答案后：
- 总结关键发现
- 记录根因（如果是在排查问题）
- 更新 memory（对可复用经验）

## 参考来源

{c["ref"]}

---
_由 skills_distiller.py 于 {datetime.now().strftime("%Y-%m-%d %H:%M")} 自动蒸馏_
"""
        skill_file.write_text(skill_content, encoding="utf-8")
        created.append(c["name"])
        print(f"  ✅ {c['name']} — SKILL.md 已生成")

    print(f"\n蒸馏完成: 新增 {len(created)} 个技能")


def print_status():
    """打印技能安装概况。"""
    existing = sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())
    patterns = _parse_interaction_patterns()
    candidates = _find_unskilled_patterns()

    print(f"技能总数: {len(existing)}")
    print(f"交互模式片段: {len(patterns)}")
    print(f"待蒸馏候选: {len(candidates)}")
    print()
    if candidates:
        print("待蒸馏:")
        for c in candidates:
            print(f"  - {c['name']}: {c['title']}")


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    if not args or args[0] in ("--list", "-l"):
        list_candidates()
    elif args[0] in ("--distill", "-d"):
        distill_all()
    elif args[0] in ("--status", "-s"):
        print_status()
    else:
        print("用法: python skills_distiller.py [--list|--distill|--status]")


if __name__ == "__main__":
    main()
