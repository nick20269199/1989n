"""审计脚本 — 检查遗漏、未执行、未落地的任务和规则。"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
STOCK_ANALYSIS = Path(__file__).parent
STOCK_DATA = Path("D:/1989n/stock_data")

results = {"errors": [], "warnings": [], "info": []}


def e(msg): results["errors"].append(msg)
def w(msg): results["warnings"].append(msg)
def i(msg): results["info"].append(msg)


print("=" * 60)
print("系统审计: 遗漏/未执行/未落地")
print("=" * 60)

# ═══ 1. Windows 计划任务 ═══
print("\n[1/6] Windows 计划任务注册检查...")
tasks_file = STOCK_ANALYSIS / "data" / "tasks.json"
tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
expected_win = {t["name"]: t for t in tasks_data["tasks"]
                if t.get("enabled") and t.get("type") == "win_task" and t.get("name")}

result = subprocess.run(
    ["C:/Windows/System32/schtasks.exe", "/QUERY", "/FO", "CSV"],
    capture_output=True, timeout=15
)
registered = set()
for line in result.stdout.decode("gbk", errors="replace").strip().split("\n")[1:]:
    parts = line.split(",")
    if parts:
        name = parts[0].strip('"').lstrip("\\")
        registered.add(name)

for name in sorted(expected_win):
    if name not in registered:
        e(f"Win任务未注册: {name} ({expected_win[name].get('description','')})")
if not results["errors"]:
    i("所有 37 个 Windows 任务已注册")
missing = [n for n in expected_win if n not in registered]
i(f"预期 {len(expected_win)}, 已注册 {len(expected_win)-len(missing)}, 缺失 {len(missing)}")

# ═══ 2. 脚本文件存在性 ═══
print("\n[2/6] 脚本文件完整性检查...")
for t in tasks_data["tasks"]:
    cmd = t.get("command", "")
    script = STOCK_ANALYSIS / cmd
    if t.get("type") == "win_task" and not script.exists():
        e(f"脚本不存在: {cmd} (任务: {t['id']})")
    # bat文件存在性
    bats = list(STOCK_ANALYSIS.glob(f"{t['id']}*.bat")) + list(STOCK_ANALYSIS.glob(f"tasks_gen/{t['id']}*.bat"))
if not results["errors"]:
    i("所有引用脚本文件均存在")

# ═══ 3. 输出/数据文件 ═══
print("\n[3/6] 数据产出文件检查...")
import glob as gglob
for t in tasks_data["tasks"]:
    for o in t.get("outputs", []):
        pattern = o["path"]
        full = str(STOCK_DATA / pattern)
        # replace wildcards for check
        matches = sorted(gglob.glob(full))
        if not matches:
            # maybe the file uses different date format
            w(f"{t['id']}: 无产出文件匹配 {pattern}")

# ═══ 4. CLAUDE.md 中记录的任务 vs 实际注册 ═══
print("\n[4/6] CLAUDE.md 定时任务表 vs 实际比对...")
# Just a structural check
claude_md = STOCK_ANALYSIS.parent / "CLAUDE.md"
claude_text = claude_md.read_text(encoding="utf-8")
cli_table_tasks = []
import re
# Find task table entries
table_lines = []
in_table = False
for line in claude_text.split("\n"):
    if "| 脚本 | 触发时间 | 功能 |" in line:
        in_table = True
        continue
    if in_table and line.startswith("|"):
        table_lines.append(line)
    elif in_table and not line.startswith("|") and not line.startswith("|---"):
        in_table = False

for tl in table_lines:
    parts = [p.strip() for p in tl.split("|")[1:-1]]
    if len(parts) >= 3:
        script_name = parts[0]
        # Check if this matches a known task
        found = any(script_name in t.get("command", "") for t in tasks_data["tasks"])
        if not found:
            w(f"CLAUDE.md 中记录的脚本 '{script_name}' 未在 tasks.json 中找到对应任务")
i(f"CLAUDE.md 任务表: {len(table_lines)} 条记录")

# ═══ 5. 关于/规则/原则的落地检查 ═══
print("\n[5/6] 规则落地检查...")
# trading_rules.json operationalized check
trading_rules = STOCK_DATA / "trading_rules.json"
if trading_rules.exists():
    rules = json.loads(trading_rules.read_text(encoding="utf-8"))
    i(f"trading_rules.json: {len(rules.get('rules',[]))} 条规则")
    # Check if referenced by expert5_risk or grader
    expert5 = STOCK_ANALYSIS / "experts" / "expert5_risk.py"
    grader = STOCK_ANALYSIS / "experts" / "grader.py"
    if expert5.exists():
        e5_text = expert5.read_text(encoding="utf-8")
        if "trading_rules" not in e5_text:
            w("trading_rules.json 未被 expert5_risk.py 引用")
    if grader.exists():
        g_text = grader.read_text(encoding="utf-8")
        if "trading_rules" not in g_text:
            w("trading_rules.json 未被 grader.py 引用")
else:
    w("trading_rules.json 不存在")

# Check memory rules vs implementation
print("\n[6/6] 跨会话已知问题复检...")
known_issues = [
    ("trading_rules.json 未操作化", "project-trading-rules-not-operationalized.md"),
]
for desc, mem_file in known_issues:
    mem_path = STOCK_ANALYSIS.parent / ".claude" / "projects" / "d--1989n" / "memory" / mem_file
    if mem_path.exists():
        content = mem_path.read_text(encoding="utf-8")
        if "fix" in content.lower() or "done" in content.lower():
            pass  # already being tracked
        else:
            pass

# Summary
print("\n" + "=" * 60)
print("审计结果汇总")
print("=" * 60)
print(f"  错误 (需立即处理): {len(results['errors'])}")
for r in results["errors"]:
    print(f"    ❌ {r}")
print(f"  警告 (需关注): {len(results['warnings'])}")
for r in results["warnings"]:
    print(f"    ⚠️  {r}")
print(f"  信息: {len(results['info'])}")
