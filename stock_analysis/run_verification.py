#!/usr/bin/env python3
"""强制任务路由器验收脚本 — 20 项验收测试"""
import yaml, json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
cases = yaml.safe_load(open(BASE / 'test_cases.yaml'))['test_cases']
router = Path('D:/1989n/task-router/task_router.py')

results = []
for case in cases:
    proc = subprocess.run(
        [sys.executable, str(router), case['description']],
        capture_output=True, text=True,
    )
    output = json.loads(proc.stdout)

    is_routed = output['status'] == 'routed'
    match = (
        set(output['agents']) == set(case['expected_agents'])
        and set(output['skills']) == set(case['expected_skills'])
        and is_routed == case['should_be_routed']
    )
    results.append({
        'id': case['id'],
        'description': case['description'],
        'expected': case,
        'actual': output,
        'pass': match,
    })

with open(BASE / 'verification_log.txt', 'w', encoding='utf-8') as f:
    f.write(f"强制任务路由器验收报告\n")
    f.write(f"时间: 2026-05-28\n")
    f.write(f"路由路径: {router}\n")
    f.write(f"用例数: {len(results)}\n\n")
    for r in results:
        status = 'PASS' if r['pass'] else 'FAIL'
        f.write(f"ID {r['id']:>2}: {status} | {r['description']}\n")
        if not r['pass']:
            f.write(f"  Expected → agents={r['expected']['expected_agents']}, "
                    f"skills={r['expected']['expected_skills']}, "
                    f"routed={r['expected']['should_be_routed']}\n")
            f.write(f"  Actual   → agents={r['actual']['agents']}, "
                    f"skills={r['actual']['skills']}, "
                    f"status={r['actual']['status']}\n")

accuracy = sum(r['pass'] for r in results) / len(results)
n_pass = sum(r['pass'] for r in results)
print(f"准确率: {accuracy:.0%} ({n_pass}/{len(results)})\n")
for r in results:
    mark = '✓' if r['pass'] else '✗'
    print(f"  {mark} #{r['id']:>2} | {r['description']}")
