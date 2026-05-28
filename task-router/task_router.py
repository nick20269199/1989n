#!/usr/bin/env python3
"""强制任务路由器。输入任务描述，输出应调用的 Agent/Skill 列表。"""
import sys, json, yaml, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROUTE_DIR = BASE_DIR

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def match_task(description: str):
    route_map = load_yaml(ROUTE_DIR / 'route_map.yaml')
    blocked = load_yaml(ROUTE_DIR / 'blocked_actions.yaml')

    agents = []
    skills = []

    # 关键词匹配
    for entry in route_map.get('routes', []):
        for kw in entry.get('keywords', []):
            if kw.lower() in description.lower():
                if entry.get('agent'):
                    agents.append(entry['agent'])
                if entry.get('skill'):
                    skills.append(entry['skill'])
                break

    # 正则匹配
    for entry in route_map.get('regex_routes', []):
        if re.search(entry['pattern'], description, re.IGNORECASE):
            if entry.get('agent'):
                agents.append(entry['agent'])
            if entry.get('skill'):
                skills.append(entry['skill'])

    agents = list(dict.fromkeys(agents))
    skills = list(dict.fromkeys(skills))

    # 高危检查
    has_blocked = any(re.search(p, description, re.IGNORECASE) for p in blocked.get('blocked_patterns', []))
    if has_blocked and not agents and not skills:
        return {
            "status": "blocked",
            "agents": [],
            "skills": [],
            "retry": False,
            "timeout_seconds": 0,
            "reason": "检测到高危操作且未匹配到负责Agent，禁止直接执行。请向协调Agent澄清。",
            "fallback_agent": "coordinator-agent"
        }
    if not agents and not skills:
        return {
            "status": "allow_direct",
            "agents": [],
            "skills": [],
            "retry": False,
            "timeout_seconds": 0,
            "reason": "未匹配到专用Agent，且无高危操作，允许直接处理。",
            "fallback_agent": None
        }
    return {
        "status": "routed",
        "agents": agents,
        "skills": skills,
        "retry": True,
        "timeout_seconds": 180,
        "reason": f"匹配到 {len(agents)} 个Agent, {len(skills)} 个Skill",
        "fallback_agent": "coordinator-agent"
    }

if __name__ == "__main__":
    desc = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    result = match_task(desc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
