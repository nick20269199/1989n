"""
bug_pattern_miner.py — Bug 模式挖掘

从现有错误数据中聚合重复错误模式，生成候选项供工程部审核。
输入: last_error.txt, error_kb_index.json, 门禁/一致性报告
输出: stock_data/status/pending_patterns.json

用法:
    python tools/bug_pattern_miner.py              # 全量挖掘
    python tools/bug_pattern_miner.py --json       # JSON 输出
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
STATUS_DIR = STOCK_DATA / "status"
TOOLS_DIR = Path(__file__).resolve().parent
PENDING_FILE = STATUS_DIR / "pending_patterns.json"


def _ensure_status_dir():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)


def load_error_kb() -> dict:
    """加载现有错误知识库。"""
    path = STATUS_DIR / "error_kb_index.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "patterns": []}


def load_last_error() -> dict | None:
    """读取 last_error.txt，提取结构化信息。"""
    path = STOCK_DATA / "last_error.txt"
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return None

    result = {
        "raw": text[:2000],
        "length": len(text),
        "file": None,
        "line": None,
        "error_type": None,
        "error_msg": None,
    }

    # 提取文件名和行号 (Traceback 格式)
    m = re.search(r'File "([^"]+)", line (\d+)', text)
    if m:
        result["file"] = m.group(1)
        result["line"] = int(m.group(2))

    # 提取错误类型
    m = re.search(r'(\w+(?:Error|Exception|Warning|Syntax|Fault))', text)
    if m:
        result["error_type"] = m.group(1)

    # 从 traceback 提取错误消息 (找第一个 Error/Exception 行的后半部分)
    m = re.search(r'(\w+(?:Error|Exception)):\s*(.+)', text)
    if m:
        result["error_type"] = m.group(1)
        result["error_msg"] = m.group(2).strip()[:500]

    return result


def match_existing_patterns(error_data: dict, kb: dict) -> list[dict]:
    """将错误数据与已有模式匹配。"""
    matches = []
    for pattern in kb.get("patterns", []):
        match_def = pattern.get("match", {})

        # any_script = 适用于所有脚本
        if match_def.get("any_script"):
            # 检查 error_text_contains
            text_checks = match_def.get("error_text_contains", [])
            if text_checks and error_data.get("error_msg"):
                if any(kw in error_data["error_msg"] for kw in text_checks):
                    matches.append(pattern)
                    continue

            # 检查 error_type_contains
            type_checks = match_def.get("error_type_contains", [])
            if type_checks and error_data.get("error_type"):
                if any(kw in error_data["error_type"] for kw in type_checks):
                    matches.append(pattern)
                    continue

        # 脚本特定匹配
        script_checks = match_def.get("script_contains", [])
        if script_checks and error_data.get("file"):
            if any(s in error_data["file"] for s in script_checks):
                # 再加文本/类型检查
                text_checks = match_def.get("error_text_contains", [])
                type_checks = match_def.get("error_type_contains", [])
                msg = error_data.get("error_msg", "")
                et = error_data.get("error_type", "")
                if (not text_checks or any(kw in msg for kw in text_checks)) and \
                   (not type_checks or any(kw in et for kw in type_checks)):
                    matches.append(pattern)
                    continue

    return matches


def extract_new_patterns(last_error: dict | None,
                         kb: dict,
                         consistency_report: dict | None = None) -> list[dict]:
    """从未编录的错误中提取候选模式。"""
    candidates = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if last_error:
        matches = match_existing_patterns(last_error, kb)
        if not matches and last_error.get("error_type"):
            # 未匹配到任何已知模式 → 候选
            candidates.append({
                "id": f"uncatalogued_{last_error['error_type'].lower()}_{now[:10]}",
                "description": f"未编录错误: {last_error['error_type']}",
                "source": "last_error.txt",
                "evidence": {
                    "file": last_error.get("file"),
                    "error_type": last_error.get("error_type"),
                    "error_msg": last_error.get("error_msg"),
                },
                "occurrences": 1,
                "suggested_match": {
                    "script_contains": [last_error.get("file", "").split("\\")[-1].replace(".py", "")]
                    if last_error.get("file") else [],
                    "error_type_contains": [last_error["error_type"]],
                },
                "created": now,
            })

    # 从一致性报告提取系统性问题
    if consistency_report:
        for detail in consistency_report.get("details", []):
            if detail.get("status") == "violation":
                candidates.append({
                    "id": f"consistency_{detail['check']}_{now[:10]}",
                    "description": f"一致性违规: {detail['check']}",
                    "source": "consistency_gate",
                    "evidence": {
                        "check": detail["check"],
                        "detail": detail.get("detail"),
                    },
                    "occurrences": 1,
                    "suggested_match": {
                        "any_script": True,
                        "error_text_contains": [detail["check"]],
                    },
                    "created": now,
                })

    return candidates


def run_mining() -> dict:
    """执行模式挖掘，并标记重复出现 3+ 次的模式为自动阻断。"""
    _ensure_status_dir()
    kb = load_error_kb()
    last_error = load_last_error()

    # 尝试加载一致性报告
    consistency_report = None
    consistency_path = STATUS_DIR / "consistency_report.json"
    if consistency_path.exists():
        try:
            consistency_report = json.loads(consistency_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    candidates = extract_new_patterns(last_error, kb, consistency_report)

    # 加载已有候选，合并去重 — 重复的累加 occurrence
    existing = []
    if PENDING_FILE.exists():
        try:
            existing = json.loads(PENDING_FILE.read_text(encoding="utf-8")).get("candidates", [])
        except Exception:
            pass

    existing_by_id = {c["id"]: c for c in existing}
    for c in candidates:
        if c["id"] in existing_by_id:
            existing_by_id[c["id"]]["occurrences"] += 1
            existing_by_id[c["id"]]["last_seen"] = c["created"]
        else:
            existing_by_id[c["id"]] = c

    merged = list(existing_by_id.values())

    # 自动阻断标记: occurrence >= 3 → P0 阻断
    auto_blocked = []
    AUTO_BLOCK_THRESHOLD = 3
    for c in merged:
        if c.get("occurrences", 0) >= AUTO_BLOCK_THRESHOLD:
            c["auto_block"] = True
            c["severity"] = "P0"
            if "auto_block" not in c.get("description", ""):
                c["description"] = f"[AUTO-BLOCK] {c['description']}"
            auto_blocked.append(c)

    result = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kb_patterns": len(kb.get("patterns", [])),
        "last_error_analyzed": last_error is not None,
        "last_error_matched": len(match_existing_patterns(last_error, kb)) > 0 if last_error else None,
        "candidates_total": len(merged),
        "candidates_new": len(candidates),
        "auto_blocked": len(auto_blocked),
        "auto_blocked_ids": [c["id"] for c in auto_blocked],
        "candidates": merged,
    }

    # 写 pending_patterns.json
    PENDING_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return result


def main():
    as_json = "--json" in sys.argv
    result = run_mining()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        kb_count = result["kb_patterns"]
        new_c = result["candidates_new"]
        total_c = result["candidates_total"]
        auto_blocked = result.get("auto_blocked", 0)
        print(f"[BUG_PATTERN_MINER] 知识库 {kb_count} 个模式")
        print(f"[BUG_PATTERN_MINER] 新增候选: {new_c}, 累计: {total_c}, 自动阻断: {auto_blocked}")
        if result.get("last_error_analyzed"):
            print(f"[BUG_PATTERN_MINER] last_error.txt 已分析"
                  f"{' (匹配已知模式)' if result.get('last_error_matched') else ' (未匹配, 生成了候选)'}")
        if auto_blocked > 0:
            print(f"[BUG_PATTERN_MINER] P0 自动阻断模式:")
            for bid in result.get("auto_blocked_ids", []):
                print(f"  🚫 {bid}")
        if new_c > 0:
            print(f"[BUG_PATTERN_MINER] 新候选写入 {PENDING_FILE}")
            for c in result["candidates"][-new_c:]:
                print(f"  ➜ {c['id']}: {c['description']}")

    sys.exit(0)


if __name__ == "__main__":
    main()
