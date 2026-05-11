"""
蒸馏队列 — 追踪每日产出，生成蒸馏简报，供 Claude 下次会话处理

流水线:
1. 每天收盘后运行 → 扫描当日新产出 → 加入蒸馏队列
2. 生成 distillation_brief.md → Claude 下次会话读取
3. Claude 处理简报 → 提取可复用知识 → 更新 rules/skills/memory
4. git_auto_push.py → 推送更新到 GitHub

运行时机: 15:45 (收盘后) + 23:45 (隔夜后)
"""
import json
import os
from datetime import datetime, date
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
INBOX = Path("D:/1989n/inbox")
QUEUE_FILE = STOCK_DATA / "distill_queue.json"
BRIEF_FILE = STOCK_DATA / "distillation_brief.md"

# 哪些文件类型需要蒸馏
DISTILL_PATTERNS = [
    "closing_review.json",       # 收盘复盘
    "morning_enhanced.json",     # 盘前简报
    "analysis_30min_*.json",     # 盘中分析
    "overnight_*.json",          # 隔夜分析
    "tech_scan_*.json",          # 技术扫描
    "nightly_plan_*.json",       # 隔夜计划
    "call_auction_*.json",       # 集合竞价
    "last_error.txt",            # 报错日志
    "git_push.log",              # 推送日志
    "trading_rules.json",        # 交易规则变更
    "sentinel_status.json",      # 任务执行状态
    "bs_analysis.json",          # 买卖分析
    "emotional_cycle_raw.json",  # 情绪周期
    "inbox/ideas.md",            # 收件箱-想法
    "inbox/links.md",            # 收件箱-链接
    "inbox/questions.md",        # 收件箱-问题
]

# 不蒸馏的（纯缓存/原始数据）
SKIP_PATTERNS = [
    "index_cache",
    "north_flow_cache",
    "market_calendar",
    "vv_video",
    "vv_ssr",
    "bilibili",
    "douyin",
    ".lock",
    ".sentinel",
]


def find_today_files() -> list[dict]:
    """扫描 stock_data/ 下今天的文件"""
    today = date.today()
    results = []

    for root, dirs, files in os.walk(STOCK_DATA):
        dirs[:] = [d for d in dirs if d not in ("vv_browser_state", ".sentinel", "__pycache__")]

        for f in files:
            fpath = Path(root) / f
            rel = fpath.relative_to(STOCK_DATA)
            rel_str = str(rel).replace("\\", "/")

            # 跳过应忽略的
            if any(p in rel_str for p in SKIP_PATTERNS):
                continue
            if f.endswith((".mp4", ".m4a", ".mp3", ".wav", ".webm", ".db")):
                continue

            try:
                mtime = datetime.fromtimestamp(fpath.stat().st_mtime).date()
                if mtime == today:
                    size_kb = fpath.stat().st_size / 1024
                    results.append({
                        "path": rel_str,
                        "size_kb": round(size_kb, 1),
                        "matched": any(p.replace("*", "") in f for p in DISTILL_PATTERNS),
                    })
            except OSError:
                continue

    # 也扫描 inbox/
    for root, dirs, files in os.walk(INBOX):
        for f in files:
            if f == ".gitkeep" or f == "README.md":
                continue
            fpath = Path(root) / f
            rel_str = "inbox/" + str(fpath.relative_to(INBOX)).replace("\\", "/")

            try:
                mtime = datetime.fromtimestamp(fpath.stat().st_mtime).date()
                if mtime == today:
                    size_kb = fpath.stat().st_size / 1024
                    matched = any(p.replace("*", "") in f for p in DISTILL_PATTERNS)
                    results.append({
                        "path": rel_str,
                        "size_kb": round(size_kb, 1),
                        "matched": matched,
                    })
            except OSError:
                continue

    return sorted(results, key=lambda x: x["matched"], reverse=True)


def load_queue() -> dict:
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    return {"entries": [], "last_distilled": None}


def save_queue(queue: dict):
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_brief(today_files: list[dict], queue: dict) -> str:
    """生成蒸馏简报 — Claude 下次会话读取"""
    today = date.today().isoformat()

    matched = [f for f in today_files if f["matched"]]
    unmatched = [f for f in today_files if not f["matched"]]

    lines = [
        f"# 蒸馏简报 — {today}",
        "",
        "## 待蒸馏文件 (匹配规则)",
        "",
    ]

    if matched:
        for f in matched:
            lines.append(f"- `{f['path']}` ({f['size_kb']}KB)")
        lines.append(f"\n共 {len(matched)} 个文件待蒸馏")
    else:
        lines.append("无")

    lines += ["", "## 今日其他产出", ""]
    if unmatched:
        for f in unmatched[:20]:  # 最多显示20个
            lines.append(f"- `{f['path']}` ({f['size_kb']}KB)")
        if len(unmatched) > 20:
            lines.append(f"\n... 还有 {len(unmatched) - 20} 个文件")
    else:
        lines.append("无")

    # 队列积压
    pending = queue.get("entries", [])
    if pending:
        lines += ["", "## 队列积压 (未蒸馏)", ""]
        for entry in pending[-5:]:  # 最近5条
            lines.append(f"- {entry['date']}: {entry['file']}")
        if len(pending) > 5:
            lines.append(f"\n... 还有 {len(pending) - 5} 条")

    lines += [
        "",
        "---",
        "",
        "## Claude 处理指令",
        "",
        "读取本简报后，按以下步骤蒸馏:",
        "",
        "1. 读取每个「待蒸馏文件」的内容",
        "2. 判断是否产生可复用知识:",
        "   - **错误模式**: 新的报错类型/根因/修复方式 → 更新 rules/ 或 memory/feedback/",
        "   - **市场规律**: 被验证的技术形态/板块轮动规律 → 更新 knowledge/stocks/",
        "   - **决策优化**: 交易决策中暴露的认知偏差 → 更新 rules/ 或 skills/",
        "   - **数据发现**: API 变化/新数据源/数据质量问题 → 更新 knowledge/tools/",
        "3. 如产生新知识 → 更新对应的 rules/skills/memory 文件 → 标记队列条目为 done",
        "4. 如无新知识 → 标记队列条目为 skipped",
        "5. 推送更新到 GitHub (git_auto_push.py)",
        "",
        f"> 生成时间: {datetime.now():%Y-%m-%d %H:%M}",
    ]

    return "\n".join(lines)


def main():
    today = date.today().isoformat()

    # 1. 扫描今日文件
    today_files = find_today_files()
    if not today_files:
        print(f"[{today}] 今日无新产出，跳过蒸馏")
        return

    # 2. 加载队列, 添加匹配的文件
    queue = load_queue()
    matched = [f for f in today_files if f["matched"]]

    for f in matched:
        # 避免重复添加
        already = any(
            e["file"] == f["path"] and e["date"] == today
            for e in queue["entries"]
        )
        if not already:
            queue["entries"].append({
                "date": today,
                "file": f["path"],
                "status": "pending",
                "size_kb": f["size_kb"],
            })

    save_queue(queue)

    # 3. 生成简报
    brief = generate_brief(today_files, queue)
    BRIEF_FILE.write_text(brief, encoding="utf-8")

    matched_count = len(matched)
    total_pending = sum(1 for e in queue["entries"] if e["status"] == "pending")
    print(f"[{today}] 蒸馏简报已生成: {matched_count} 文件匹配, 队列共 {total_pending} 待处理")


if __name__ == "__main__":
    main()
