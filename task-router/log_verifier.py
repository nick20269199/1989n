#!/usr/bin/env python3
"""日志一致性校验 — 每轮对话后外部查验。

功能:
  1. 扫描 agent_exec/ 最近 2 天日志
  2. 随机抽 3 条，校验必含字段完整性
  3. 输出 PASS/FAIL 报告
  4. 连续两次 FAIL 会写入告警标记 (飞书告警后续集成)
"""
import json, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_BASE = Path("d:/1989n/logs/agent_exec")
ALERT_FLAG = Path("d:/1989n/logs/.log_verifier_fail_count")

REQUIRED_FIELDS = ["task", "hostname", "start_time", "end_time", "exit_code",
                   "output_summary", "output_hash", "agent", "skill"]


def scan_recent_logs(days: int = 2) -> list[dict]:
    """扫描最近 N 天所有 Agent 日志，返回记录列表。"""
    records = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for d in sorted(LOG_BASE.iterdir()):
        if not d.is_dir():
            continue
        try:
            day = datetime.strptime(d.name, "%Y-%m-%d").date()
            if datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict):
                    records.append(data)
            except (json.JSONDecodeError, Exception):
                pass
    return records


def verify_record(rec: dict) -> tuple[bool, list[str]]:
    """校验单条记录是否包含所有必含字段且值非空 (exit_code=0 视为有效)。"""
    missing = []
    for f in REQUIRED_FIELDS:
        if f not in rec:
            missing.append(f)
        elif isinstance(rec[f], (int, float)):
            continue  # 数值 0 是有效值
        elif not rec[f]:
            missing.append(f)
    return (len(missing) == 0, missing)


def run_check() -> dict:
    """执行一次全面校验。"""
    if not LOG_BASE.exists():
        return {"status": "SKIP", "reason": f"日志目录 {LOG_BASE} 不存在", "sampled": 0, "passed": 0, "failed": 0}

    records = scan_recent_logs()
    if not records:
        return {"status": "SKIP", "reason": "最近2天无日志记录", "sampled": 0, "passed": 0, "failed": 0}

    sample = random.sample(records, min(3, len(records)))
    passed = 0
    failed = 0
    details = []

    for rec in sample:
        ok, missing = verify_record(rec)
        if ok:
            passed += 1
            details.append({"agent": rec.get("agent"), "status": "PASS"})
        else:
            failed += 1
            details.append({"agent": rec.get("agent"), "status": "FAIL", "missing": missing})

    status = "PASS" if failed == 0 else "FAIL"
    result = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sampled": len(sample),
        "passed": passed,
        "failed": failed,
        "details": details,
    }

    # 连续失败计数
    fail_count = 0
    if ALERT_FLAG.exists():
        try:
            fail_count = int(ALERT_FLAG.read_text().strip())
        except (ValueError, Exception):
            fail_count = 0

    if status == "FAIL":
        fail_count += 1
        if fail_count >= 2:
            result["alert"] = "连续两次不一致，需要飞书告警+暂停对话"
            fail_count = 0  # 告警后重置
    else:
        fail_count = 0

    ALERT_FLAG.parent.mkdir(parents=True, exist_ok=True)
    ALERT_FLAG.write_text(str(fail_count))
    return result


if __name__ == "__main__":
    result = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("status") in ("PASS", "SKIP") else 1)
