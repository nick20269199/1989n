"""
feedback_miner.py — 反馈→规则转换

扫描 feedback 记忆文件，提取可编码为自动检查的规则。
输出 actionable_feedback.json 供工程部审核。

用法:
    python tools/feedback_miner.py              # 扫描并输出
    python tools/feedback_miner.py --json       # JSON 输出
"""
import json
import re
import sys
from pathlib import Path

MEMORY_DIR = Path("D:/1989n/.claude/memory")
STATUS_DIR = Path("D:/1989n/stock_data/status")
OUTPUT_FILE = STATUS_DIR / "actionable_feedback.json"

# 可以编码为自动检查的关键词
ACTIONABLE_KEYWORDS = [
    "必须", "禁止", "不允许", "需要", "确保", "检查", "验证",
    "先查", "先读", "不要", "不能", "一定要",
    "must", "never", "always", "required", "mandatory",
    "P0", "P1", "铁律", "硬约束",
]

# 检查类型分类
CHECK_TYPES = {
    "syntax": ["语法", "compile", "SyntaxError", "语法门禁"],
    "schema": ["schema", "字段", "类型", "必需字段", "保鲜"],
    "test": ["测试", "pytest", "冒烟", "单元测试"],
    "consistency": ["一致性", "cross-file", "关联"],
    "error_pattern": ["错误类型", "异常", "error", "traceback"],
    "path": ["路径", "D盘", "C盘", "stock_data", "working directory"],
    "security": ["密钥", "token", ".env", "泄露"],
    "data_quality": ["数据", "校验", "格式", "空值"],
}


def scan_feedback_files() -> list[dict]:
    """扫描 feedback 文件，提取规则。"""
    if not MEMORY_DIR.exists():
        return []

    results = []
    for f in sorted(MEMORY_DIR.glob("feedback*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 解析 frontmatter
        fm = {}
        m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
        if m:
            fm_text = m.group(1)
            for line in fm_text.strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip().strip('"\'')
            text_body = text[m.end():].strip()
        else:
            text_body = text.strip()

        # 提取 description
        name = fm.get("name", f.stem)
        description = fm.get("description", "")
        metadata_type = fm.get("metadata.type", "")

        # 扫描可操作规则
        rules = []
        lines = text_body.splitlines()
        for line in lines:
            line_s = line.strip()
            if not line_s:
                continue

            # 包含可操作关键词的行
            has_keyword = any(kw in line_s for kw in ACTIONABLE_KEYWORDS)
            if not has_keyword:
                continue

            # 跳过太短的行
            if len(line_s) < 15:
                continue

            # 分类
            check_type = classify_check(line_s)

            rules.append({
                "text": line_s[:300],
                "type": check_type,
                "priority": extract_priority(line_s),
            })

        if rules or description:
            results.append({
                "file": f.name,
                "name": name,
                "description": description[:200] if description else "",
                "rules": rules,
                "rule_count": len(rules),
            })

    return results


def classify_check(text: str) -> str:
    """判断规则属于哪类检查。"""
    for ctype, keywords in CHECK_TYPES.items():
        if any(kw in text for kw in keywords):
            return ctype
    # 默认：流程类
    return "process"


def extract_priority(text: str) -> str:
    """提取优先级标记。"""
    if "P0" in text:
        return "P0"
    if "P1" in text:
        return "P1"
    if "P2" in text:
        return "P2"
    if "铁律" in text or "硬约束" in text:
        return "P0"
    if "必须" in text or "禁止" in text or "不允许" in text:
        return "P0"
    if "需要" in text or "确保" in text or "一定要" in text:
        return "P1"
    return "P2"


def build_actionable_output(scanned: list[dict]) -> dict:
    """生成 actionable 输出。"""
    all_rules = []
    file_summary = []

    for f in scanned:
        file_summary.append({
            "file": f["file"],
            "description": f["description"],
            "rules_found": f["rule_count"],
        })
        for r in f["rules"]:
            r["source"] = f["file"]
            all_rules.append(r)

    # 按类型聚合
    by_type = {}
    for r in all_rules:
        t = r["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(r)

    # 按优先级聚合
    by_priority = {}
    for r in all_rules:
        p = r["priority"]
        by_priority.setdefault(p, []).append(r)

    return {
        "generated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files_scanned": len(scanned),
        "total_rules": len(all_rules),
        "by_type": {t: len(rules) for t, rules in by_type.items()},
        "by_priority": {p: len(rules) for p, rules in by_priority.items()},
        "file_summary": file_summary,
        "p0_rules": [r for r in all_rules if r["priority"] == "P0"],
        "p1_rules": [r for r in all_rules if r["priority"] == "P1"],
    }


def main():
    as_json = "--json" in sys.argv
    STATUS_DIR.mkdir(parents=True, exist_ok=True)

    scanned = scan_feedback_files()
    output = build_actionable_output(scanned)

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if as_json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"[FEEDBACK_MINER] 扫描 {output['files_scanned']} 个 feedback 文件")
        print(f"[FEEDBACK_MINER] 提取 {output['total_rules']} 条可操作规则")
        print(f"\n  按优先级:")
        for p, count in sorted(output["by_priority"].items()):
            print(f"    {p}: {count} 条")
        print(f"\n  按类型:")
        for t, count in sorted(output["by_type"].items()):
            print(f"    {t}: {count} 条")
        if output.get("p0_rules"):
            print(f"\n  P0 规则示例:")
            for r in output["p0_rules"][:5]:
                print(f"    [{r['source']}] {r['text'][:80]}...")
        print(f"\n  输出文件: {OUTPUT_FILE}")

    sys.exit(0)


if __name__ == "__main__":
    main()
