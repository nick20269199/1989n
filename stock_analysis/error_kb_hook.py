"""
error_kb_hook.py — 错误→知识钩子 v1

在 error_capture._save_error() 末尾调用。
计算错误签名 → 匹配 error_kb_index.json → 命中则写入 hook 报告。

精确匹配链：script + error_type + error_text 三层 → 逐一降级 → 兜底。
未命中任何 pattern → 不写任何输出（零假阳性）。
"""

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

CST = timezone(timedelta(hours=8))
INDEX_PATH = Path("D:/1989n/stock_data/status/error_kb_index.json")
REPORT_PATH = Path("D:/1989n/stock_data/status/error_kb_hook_report.json")

logger = logging.getLogger("error-kb-hook")


def _load_index() -> dict:
    """加载错误签名索引。缺失/损坏 → 返回空索引。"""
    if not INDEX_PATH.exists():
        return {"version": 0, "patterns": []}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("加载 error_kb_index.json 失败: %s", e)
        return {"version": 0, "patterns": []}


def compute_signature(exc_type: type, exc_value: Exception, script_name: str) -> dict:
    """从异常中提取结构化签名。"""
    return {
        "script": script_name,
        "error_type": exc_type.__name__,
        "error_text": str(exc_value)[:300],
    }


def match_patterns(signature: dict, index: dict) -> Optional[dict]:
    """按精确度降序匹配。命中第一条即返回。"""
    patterns = index.get("patterns", [])
    if not patterns:
        return None

    sig_script = signature["script"]
    sig_type = signature["error_type"]
    sig_text = signature["error_text"]

    for pattern in patterns:
        m = pattern["match"]

        # ── 脚本匹配 ──
        if not m.get("any_script"):
            script_rules = m.get("script_contains", [])
            if not any(sc in sig_script for sc in script_rules):
                continue

        # ── 错误类型匹配 ──
        type_rules = m.get("error_type_contains", [])
        if type_rules:
            if not any(et in sig_type for et in type_rules):
                continue

        # ── 错误文本匹配 ──
        text_rules = m.get("error_text_contains", [])
        if text_rules:
            if not any(t in sig_text for t in text_rules):
                continue

        # ── 兜底: any_error 无条件匹配 ──
        if m.get("any_error"):
            return pattern

        # 所有条件满足
        return pattern

    return None


def run_hook(exc_type: type, exc_value: Exception, script_name: str) -> Optional[dict]:
    """主入口：计算签名 → 匹配 → 写报告 → 返回匹配结果。"""
    signature = compute_signature(exc_type, exc_value, script_name)
    index = _load_index()

    matched = match_patterns(signature, index)

    report = {
        "timestamp": datetime.now(CST).isoformat(),
        "signature": signature,
        "matched": matched["id"] if matched else None,
        "diagnosis": matched.get("diagnosis", "") if matched else "",
        "action": matched.get("action", "") if matched else "",
        "knowledge": matched.get("knowledge", []) if matched else [],
    }

    if matched:
        # 有匹配 → 写入报告
        try:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(
                "[error-kb-hook] 匹配 pattern=%s script=%s type=%s",
                matched["id"], script_name, signature["error_type"],
            )
        except Exception as e:
            logger.warning("写入 error_kb_hook_report.json 失败: %s", e)

        return report
    else:
        # 无匹配 → 不写文件，不留假阳性
        # 但清理旧报告（如果存在）以防止读旧数据
        if REPORT_PATH.exists():
            try:
                REPORT_PATH.unlink()
            except Exception:
                pass
        logger.info(
            "[error-kb-hook] 无匹配 script=%s type=%s text=%s...",
            script_name, signature["error_type"], signature["error_text"][:80],
        )
        return None


if __name__ == "__main__":
    # CLI test
    if len(sys.argv) >= 3:
        exc_type_name = sys.argv[1]
        exc_msg = sys.argv[2]
        script = sys.argv[3] if len(sys.argv) > 3 else "test_script.py"
        exc_type = __builtins__.get(exc_type_name, Exception) if isinstance(__builtins__, dict) else getattr(__builtins__, exc_type_name, Exception)
        exc = exc_type(exc_msg)
        result = run_hook(type(exc), exc, script)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("[error-kb-hook] 无匹配")
    else:
        print("用法: python error_kb_hook.py <ErrorType> <message> [script]")
        print("示例: python error_kb_hook.py ConnectionError 'EASTMONEY_BLOCKED' daily_task.py")
