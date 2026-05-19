"""
sync_portfolio_sources.py — 同步持仓数据到所有依赖源

功能:
  1. 读取 portfolio.json（唯一数据源）
  2. 更新 CLAUDE.md 的持仓表和已清仓表
  3. 更新 daily_task.py 的 _fallback_holdings()
  4. 报告差异

用法:
  python scripts/sync_portfolio_sources.py          # 执行同步
  python scripts/sync_portfolio_sources.py --check   # 只检查不修改
  python scripts/sync_portfolio_sources.py --ci      # 非交互模式（定时任务用）
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = PROJECT_DIR / "data" / "portfolio.json"
CLAUDE_MD = PROJECT_DIR.parent / "CLAUDE.md"
DAILY_TASK = PROJECT_DIR / "daily_task.py"

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_portfolio() -> dict:
    if not PORTFOLIO_FILE.exists():
        print(f"[ERROR] {PORTFOLIO_FILE} 不存在")
        sys.exit(1)
    data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    return data


def build_tables(data: dict) -> tuple[str, str]:
    """从 portfolio.json 数据生成持仓表和已清仓表的 markdown"""
    rows = []
    for h in data.get("holdings", []):
        code = h["code"]
        name = h["name"]
        shares = h["shares"]
        cost = h["cost"]
        sector = h.get("sector", "")
        rows.append(f"| {code} | {name} | {shares} | {cost:.3f} | {sector} |")

    holdings_table = "\n".join(rows) if rows else "(无)"

    rows2 = []
    for c in data.get("cleared", []):
        code = c["code"]
        name = c["name"]
        price = c.get("closed_price", 0)
        pnl = c.get("pnl", 0)
        closed = c.get("closed_date", "")
        rows2.append(f"| {code} | {name} | {price:.2f} | {pnl:+,} | {closed} |")

    cleared_table = "\n".join(rows2) if rows2 else "(无)"

    today_str = date.today().strftime("%Y-%m-%d")
    return holdings_table, cleared_table, today_str


def sync_claude_md(holdings_table: str, cleared_table: str, today_str: str, check_only: bool) -> bool:
    """更新 CLAUDE.md 的持仓表和已清仓表，返回是否有变更"""
    if not CLAUDE_MD.exists():
        print(f"[WARN] {CLAUDE_MD} 不存在，跳过")
        return False

    text = CLAUDE_MD.read_text(encoding="utf-8")

    # 替换 "当前持仓" 表头（更新日期）
    new_header = f"## 当前持仓 — 以 data/portfolio.json 为唯一准 (最后同步: {today_str})"
    old_header_match = re.search(r"^## 当前持仓.*$", text, re.MULTILINE)
    if old_header_match:
        text = text.replace(old_header_match.group(0), new_header)
    else:
        print("[WARN] CLAUDE.md 未找到「当前持仓」表头行")

    # 替换从 "当前持仓" 表头到 "已清仓" 表头之间的内容
    # 找到 holdings 表的范围（从表头行后到下一个二级标题）
    holdings_pattern = re.compile(
        r"(## 当前持仓.*?\n"
        r"\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*\n"  # 分隔行
        r"\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*\|.*?\|\s*"    # 数据行（可能多行）
        r")",
        re.DOTALL,
    )
    # 更精确的做法：找到表头+分隔行+数据行直到下一个 ## 或文件末尾的空白行

    lines = text.split("\n")
    new_lines = []
    in_holdings = False
    in_cleared = False
    holdings_header_found = False
    cleared_header_found = False
    holdings_done = False
    cleared_done = False
    changed = False

    for line in lines:
        # 检测当前持仓表开始
        if line.startswith("## 当前持仓"):
            in_holdings = True
            in_cleared = False
            holdings_header_found = True
            # 写新表头（可能已被替换）
            new_lines.append(new_header)
            new_lines.append("")
            new_lines.append("| 代码 | 名称 | 持仓(股) | 成本价 | 行业 |")
            new_lines.append("|------|------|---------|--------|------|")
            for row in holdings_table.split("\n"):
                new_lines.append(row)
            new_lines.append("")
            changed = True
            continue

        if line.startswith("## 已清仓"):
            in_holdings = False
            in_cleared = True
            cleared_header_found = True
            new_lines.append(line)
            new_lines.append("")
            new_lines.append("| 代码 | 名称 | 出清价 | 盈亏 | 出清日 |")
            new_lines.append("|------|------|--------|------|--------|")
            for row in cleared_table.split("\n"):
                new_lines.append(row)
            new_lines.append("")
            changed = True
            continue

        # 跳过持仓表和已清仓表区域内的旧行（已由新表替换）
        if in_holdings:
            # 跳过表头行、分隔行、数据行、空行，直到下一个 ##
            if line.startswith("|") or line == "" or line.startswith("---"):
                continue
            else:
                in_holdings = False

        if in_cleared:
            if line.startswith("|") or line == "" or line.startswith("---"):
                continue
            else:
                in_cleared = False

        if not in_holdings and not in_cleared:
            new_lines.append(line)

    new_text = "\n".join(new_lines)

    if check_only:
        if text != new_text:
            print("[CHECK] CLAUDE.md 需要更新")
            _show_diff(text, new_text)
            return True
        print("[CHECK] CLAUDE.md 已是最新")
        return False

    if text != new_text:
        CLAUDE_MD.write_text(new_text, encoding="utf-8")
        print(f"[OK] CLAUDE.md 已更新 ({today_str})")
        return True
    else:
        print("[OK] CLAUDE.md 无变更")
        return False


def sync_fallback_holdings(data: dict, check_only: bool) -> bool:
    """更新 daily_task.py 的 _fallback_holdings() 函数"""
    if not DAILY_TASK.exists():
        print(f"[WARN] {DAILY_TASK} 不存在，跳过")
        return False

    text = DAILY_TASK.read_text(encoding="utf-8")

    # 找到 _fallback_holdings 函数的范围
    match = re.search(
        r"def _fallback_holdings\(\) -> list\[dict\]:\n"
        r"(?:    .*\n)*",
        text,
    )
    if not match:
        print("[WARN] daily_task.py 未找到 _fallback_holdings 函数")
        return False

    old_func = match.group(0)

    # 构建新函数体
    lines = ['def _fallback_holdings() -> list[dict]:']
    lines.append('    """硬编码后备持仓（与 portfolio.json 一致的应急备份）"""')
    lines.append('    return [')

    for h in data.get("holdings", []):
        code = h["code"]
        name = h["name"]
        shares = h["shares"]
        cost = h["cost"]
        sector = h.get("sector", "")
        fb = h.get("first_buy", "")
        lb = h.get("latest_buy", "")
        lines.append(
            f'        {{"code": "{code}", "name": "{name}", '
            f'"shares": {shares}, "cost": {cost:.3f}, '
            f'"sector": "{sector}", '
            f'"first_buy": "{fb}", "latest_buy": "{lb}"}},'
        )

    lines.append('    ]')
    new_func = "\n".join(lines)

    if check_only:
        if old_func != new_func:
            print("[CHECK] daily_task.py _fallback_holdings 需要更新")
            _show_diff(old_func, new_func)
            return True
        print("[CHECK] daily_task.py 已是最新")
        return False

    if old_func != new_func:
        text = text.replace(old_func, new_func)
        DAILY_TASK.write_text(text, encoding="utf-8")
        print(f"[OK] daily_task.py _fallback_holdings 已更新")
        return True
    else:
        print("[OK] daily_task.py 无变更")
        return False


def _show_diff(old: str, new: str):
    """简单的行级 diff 输出"""
    old_lines = old.split("\n")
    new_lines = new.split("\n")
    for i, (o, n) in enumerate(zip(old_lines, new_lines)):
        if o != n:
            print(f"  -{o}")
            print(f"  +{n}")
    if len(old_lines) != len(new_lines):
        print(f"  (行数差异: {len(old_lines)} → {len(new_lines)})")


def register_scheduled_task():
    """注册 Windows 定时任务，每天 15:30 执行同步"""
    python = sys.executable
    script = PROJECT_DIR / "scripts" / "sync_portfolio_sources.py"
    task_name = "SyncPortfolioSources"

    import subprocess
    cmd = [
        "schtasks", "/Create", "/F", "/SC", "DAILY",
        "/TN", task_name,
        "/TR", f'"{python}" "{script}" --ci',
        "/ST", "15:30",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] 定时任务 '{task_name}' 已注册 (每天 15:30)")
    else:
        print(f"[WARN] 定时任务注册失败: {result.stderr.strip()}")


def main():
    check_only = "--check" in sys.argv
    ci_mode = "--ci" in sys.argv

    data = load_portfolio()
    holdings_table, cleared_table, today_str = build_tables(data)

    print(f"portfolio.json: {len(data.get('holdings', []))} 持仓, "
          f"{len(data.get('cleared', []))} 已清仓")
    print(f"同步日期: {today_str}")
    print()

    any_change = False

    print("[1/2] CLAUDE.md...")
    c1 = sync_claude_md(holdings_table, cleared_table, today_str, check_only)
    any_change = any_change or c1

    print()
    print("[2/2] daily_task.py _fallback_holdings...")
    c2 = sync_fallback_holdings(data, check_only)
    any_change = any_change or c2

    print()
    if check_only:
        if any_change:
            print("⚠ 有变更待同步，运行不带 --check 以执行")
            sys.exit(0)
        else:
            print("✓ 所有源已是最新")
            sys.exit(0)

    if any_change:
        print("✓ 同步完成")
    else:
        print("✓ 无需变更 (各源已一致)")

    # CI 模式下自动注册定时任务
    if ci_mode:
        print()
        register_scheduled_task()


if __name__ == "__main__":
    main()
