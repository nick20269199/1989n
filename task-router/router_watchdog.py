#!/usr/bin/env python3
"""路由器健康监控 — 检查路由配置和 Agent 执行状态。

检查项:
  1. route_map.yaml 完整性 (keyword 路由数 / regex 路由数)
  2. blocked_actions.yaml 可加载
  3. task_router.py 响应正常
  4. emergency_direct_mode.txt 是否存在 (全局应急降级状态)
  5. agent_exec 日志完整率
  6. 统计各 Agent 最近 7 天失败率
"""
import json, subprocess, sys, yaml
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_BASE = Path("d:/1989n/logs/agent_exec")
EMERGENCY_FLAG = BASE_DIR / "emergency_direct_mode.txt"


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_route_config() -> dict:
    """检查 route_map.yaml 和 blocked_actions.yaml。"""
    errors = []
    route_count = 0
    regex_count = 0

    route_map = BASE_DIR / "route_map.yaml"
    if not route_map.exists():
        return {"status": "FAIL", "errors": ["route_map.yaml 缺失"]}

    data = load_yaml(route_map)
    routes = data.get("routes", [])
    regexes = data.get("regex_routes", [])
    route_count = len(routes)
    regex_count = len(regexes)

    # 检查 keyword 路由
    for i, entry in enumerate(routes):
        if "keywords" not in entry or not entry["keywords"]:
            errors.append(f"routes[{i}] 缺少 keywords")
        if "agent" not in entry and "skill" not in entry:
            errors.append(f"routes[{i}] 缺少 agent 和 skill")

    # 检查正则路由
    for i, entry in enumerate(regexes):
        if "pattern" not in entry:
            errors.append(f"regex_routes[{i}] 缺少 pattern")

    # 检查 blocked
    blocked = BASE_DIR / "blocked_actions.yaml"
    if not blocked.exists():
        errors.append("blocked_actions.yaml 缺失")

    return {
        "status": "PASS" if not errors else "WARN",
        "routes": route_count,
        "regex_routes": regex_count,
        "errors": errors,
    }


def check_router_response() -> dict:
    """检查 task_router.py 能否正常响应。"""
    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "task_router.py"), "测试任务"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"status": "FAIL", "error": result.stderr[:200]}
        data = json.loads(result.stdout)
        return {"status": "PASS", "response": data.get("status")}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def check_emergency_mode() -> dict:
    """检查紧急降级开关状态。"""
    return {
        "active": EMERGENCY_FLAG.exists(),
        "path": str(EMERGENCY_FLAG),
    }


def check_agent_logs() -> dict:
    """检查最近 7 天各 Agent 日志完整性和失败率。"""
    if not LOG_BASE.exists():
        return {"status": "SKIP", "reason": "日志目录不存在", "agents": 0, "total_calls": 0, "fail_rate": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    agent_stats: dict[str, dict] = {}
    total = 0
    fails = 0

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
            agent_name = f.stem
            if agent_name not in agent_stats:
                agent_stats[agent_name] = {"calls": 0, "fails": 0}
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    agent_stats[agent_name]["calls"] += 1
                    total += 1
                    if rec.get("exit_code", 0) != 0:
                        agent_stats[agent_name]["fails"] += 1
                        fails += 1
            except (json.JSONDecodeError, Exception):
                pass

    fail_rate = round(fails / total * 100, 2) if total > 0 else 0
    return {
        "status": "PASS" if fail_rate <= 5 else "WARN" if fail_rate <= 10 else "FAIL",
        "agents": len(agent_stats),
        "total_calls": total,
        "fail_rate": fail_rate,
        "agent_detail": agent_stats,
    }


def run_all() -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "route_config": check_route_config(),
        "router_response": check_router_response(),
        "emergency_mode": check_emergency_mode(),
        "agent_logs": check_agent_logs(),
    }


if __name__ == "__main__":
    sys.path.insert(0, str(BASE_DIR.parent / "stock_analysis"))
    from feishu_sender import send_alert

    report = run_all()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 汇总判定
    fails = []
    for k, v in report.items():
        if isinstance(v, dict) and v.get("status") == "FAIL":
            fails.append(k)
    if fails:
        print(f"\n❌ 以下检查项 FAIL: {', '.join(fails)}")
        send_alert(f"路由器健康检查发现 FAIL 项: {', '.join(fails)}。请登录服务器查看详情。")
        sys.exit(1)
    else:
        warns = [k for k, v in report.items()
                 if isinstance(v, dict) and v.get("status") == "WARN"]
        if warns:
            print(f"\n⚠️  以下检查项 WARN: {', '.join(warns)}")
        else:
            print("\n✅ 全部检查通过")
