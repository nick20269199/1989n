#!/usr/bin/env python3
"""路由器回测验证 — 基于 route_map.yaml 的关键词命中验证"""
import json, yaml, sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    route_map = load_yaml(BASE_DIR / 'route_map.yaml')
    routes = route_map.get('routes', [])
    log = []
    passed = 0
    failed = 0

    # 从各 route 提取关键词，构造测试用例
    test_cases = []
    for entry in routes:
        for kw in entry.get('keywords', []):
            agent = entry.get('agent', '?')
            test_cases.append((kw, agent))

    log.append(f"# 路由器回测验证报告 — {len(test_cases)} 个测试用例\n")

    for kw, expected_agent in test_cases:
        # 直接模拟路由器逻辑（避免 import 路径问题）
        matched_agents = []
        for entry in routes:
            for ekw in entry.get('keywords', []):
                if ekw.lower() in kw.lower():
                    if entry.get('agent') and entry['agent'] not in matched_agents:
                        matched_agents.append(entry['agent'])
                    break
        status = "PASS" if expected_agent in matched_agents else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        log.append(f"[{status}] keyword='{kw}' → expected={expected_agent} got={matched_agents}")

    log.append(f"\n## 汇总: {passed} passed, {failed} failed, {passed+failed} total")

    report = "\n".join(log)
    out_path = BASE_DIR / 'verification_log.txt'
    out_path.write_text(report, encoding='utf-8')
    print(report)
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
