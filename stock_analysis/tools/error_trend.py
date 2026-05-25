"""
error_trend.py — 错误趋势分析

30 天滑动窗口分析错误模式：
- 哪些脚本最爱崩？
- 错误率趋势（上升/下降/平稳）
- 时段分布
- 趋势连续 3 天上升 → 预警信号

用法:
    python tools/error_trend.py              # 分析并写 error_trends.json
    python tools/error_trend.py --json       # JSON 输出到 stdout
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
STATUS_DIR = STOCK_DATA / "status"
TREND_FILE = STATUS_DIR / "error_trends.json"

NOW = datetime.now()
WINDOW_DAYS = 30


def parse_last_error_entries() -> list[dict]:
    """从 last_error.txt 解析历史错误条目。"""
    path = STOCK_DATA / "last_error.txt"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    entries = []

    # 按 === 分割后合并相邻块（timestamp 在前一块，内容在下一块）
    raw_blocks = re.split(r'={3,}', text)
    blocks = []
    for b in raw_blocks:
        b = b.strip()
        if b:
            blocks.append(b)

    i = 0
    while i < len(blocks):
        block = blocks[i]
        entry = {"timestamp": None, "script": None, "error_type": None,
                 "error_msg": None, "source": "last_error.txt"}

        # 如果当前块以时间戳开头（如 "LAST ERROR [2026-05-25 08:37:35]"），
        # 则与下一块合并
        ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', block)
        if ts_match and ("LAST ERROR" in block or "failure_analyzer" in block):
            # 可能是 header 块，与下一块合并
            if i + 1 < len(blocks):
                next_block = blocks[i + 1]
                # 如果下一块不以时间戳开头，合并
                if not re.search(r'\[?\d{4}-\d{2}-\d{2}', next_block):
                    block = block + "\n" + next_block
                    i += 1

        # 提取时间戳
        m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', block)
        if m:
            try:
                entry["timestamp"] = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").isoformat()
            except ValueError:
                pass

        # 提取脚本名
        m = re.search(r'Script:\s*(\S+)', block)
        if m:
            entry["script"] = m.group(1)

        # 从 failure_analyzer 诊断块提取文件名
        m = re.search(r'文件:\s*(\S+)', block)
        if m:
            fname = m.group(1).split("\\")[-1]
            fname = fname.split(":")[0].replace(".py", "")
            entry["script"] = fname

        # 从 Traceback File 行提取脚本名
        if not entry["script"]:
            m = re.findall(r'File\s+"([^"]+)"', block)
            if m:
                for fp in m:
                    fname = fp.split("\\")[-1].replace(".py", "")
                    if fname and fname != "<module>":
                        entry["script"] = fname
                        break

        # 从 Traceback 提取错误类型和消息
        m = re.search(r'(\w+(?:Error|Exception)):\s*(.+)', block)
        if m:
            entry["error_type"] = m.group(1)
            entry["error_msg"] = m.group(2).strip()[:300]

        # 从 failure_analyzer 诊断块提取
        m = re.search(r'根因类别:\s*(\S+)', block)
        if m:
            entry["category"] = m.group(1)
        m = re.search(r'详情:\s*(.+)', block)
        if m:
            detail = m.group(1).strip()
            if detail and detail != "u" and len(detail) > 1:
                if ":" in detail:
                    entry["error_type"] = detail.split(":")[0].strip()
                elif not entry.get("error_type"):
                    entry["error_type"] = detail[:200]

        if entry.get("error_type") or entry.get("category"):
            entries.append(entry)

        i += 1

    return entries


def compute_trends(entries: list[dict]) -> dict:
    """计算 30 天滑动窗口内的错误趋势。"""
    now = NOW
    window_start = now - timedelta(days=WINDOW_DAYS)

    # 过滤窗口内
    windowed = []
    for e in entries:
        ts = e.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt >= window_start:
                    windowed.append(e)
            except ValueError:
                pass

    # 脚本分布
    script_counts = Counter()
    for e in windowed:
        script = e.get("script") or e.get("file", "unknown")
        # 从文件路径提取脚本名
        if "\\" in script:
            script = script.split("\\")[-1]
        script_counts[script] += 1

    # 错误类型分布
    type_counts = Counter()
    for e in windowed:
        t = e.get("error_type") or e.get("category", "unknown")
        type_counts[t] += 1

    # 时段分布 (每小时)
    hour_counts = Counter()
    for e in windowed:
        ts = e.get("timestamp")
        if ts:
            try:
                hour = datetime.fromisoformat(ts).hour
                hour_counts[hour] += 1
            except ValueError:
                pass

    # 日趋势 (每天错误数)
    day_trend = Counter()
    for e in windowed:
        ts = e.get("timestamp")
        if ts:
            try:
                day = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
                day_trend[day] += 1
            except ValueError:
                pass

    # 趋势方向: 比较最后 7 天 vs 前 7 天
    last_7 = now - timedelta(days=7)
    prev_7_start = now - timedelta(days=14)
    prev_7_end = now - timedelta(days=7)

    last_7_count = sum(1 for e in windowed if e.get("timestamp") and
                       datetime.fromisoformat(e["timestamp"]) >= last_7)
    prev_7_count = sum(1 for e in windowed if e.get("timestamp") and
                       prev_7_start <= datetime.fromisoformat(e["timestamp"]) < prev_7_end)

    if prev_7_count == 0:
        direction = "stable" if last_7_count == 0 else "up"
        change_pct = 100 if last_7_count > 0 else 0
    else:
        change_pct = round((last_7_count - prev_7_count) / prev_7_count * 100, 1)
        if change_pct > 20:
            direction = "up"
        elif change_pct < -20:
            direction = "down"
        else:
            direction = "stable"

    # 按日排序的趋势数据
    sorted_days = sorted(day_trend.items())

    return {
        "window_days": WINDOW_DAYS,
        "analyzed_at": now.isoformat(),
        "total_entries_in_window": len(windowed),
        "direction": direction,
        "change_pct": change_pct,
        "last_7_count": last_7_count,
        "prev_7_count": prev_7_count,
        "alert": direction == "up" and last_7_count >= 3,
        "top_scripts": [{"script": s, "count": c} for s, c in script_counts.most_common(10)],
        "top_error_types": [{"type": t, "count": c} for t, c in type_counts.most_common(10)],
        "hour_distribution": [{"hour": h, "count": c} for h, c in sorted(hour_counts.items())],
        "day_trend": [{"date": d, "count": c} for d, c in sorted_days],
    }


def run_analysis() -> dict:
    """执行趋势分析并写文件。"""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    entries = parse_last_error_entries()
    trends = compute_trends(entries)

    # 合并历史趋势
    previous = None
    if TREND_FILE.exists():
        try:
            previous = json.loads(TREND_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    if previous:
        trends["previous"] = {
            "analyzed_at": previous.get("analyzed_at"),
            "direction": previous.get("direction"),
            "total_entries_in_window": previous.get("total_entries_in_window"),
        }

    TREND_FILE.write_text(
        json.dumps(trends, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return trends


def main():
    as_json = "--json" in sys.argv
    result = run_analysis()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[ERROR_TREND] 30天窗口: {result['total_entries_in_window']} 条错误记录")
        print(f"[ERROR_TREND] 趋势方向: {result['direction']} "
              f"(前后7天对比: {result['change_pct']:+.1f}%)")
        if result.get("alert"):
            print(f"[ERROR_TREND] ⚠ 预警: 后7天错误 {result['last_7_count']} 次，趋势上升")

        print(f"\n  常见脚本:")
        for s in result.get("top_scripts", [])[:5]:
            print(f"    {s['script']}: {s['count']} 次")

        print(f"\n  常见错误类型:")
        for t in result.get("top_error_types", [])[:5]:
            print(f"    {t['type']}: {t['count']} 次")

        print(f"\n  时段分布 (交易时段):")
        for h in result.get("hour_distribution", []):
            if 8 <= h["hour"] <= 15:
                print(f"    {h['hour']:02d}:00 — {h['count']} 次")

        print(f"\n  趋势文件: {TREND_FILE}")

    sys.exit(0 if not result.get("alert") else 1)


if __name__ == "__main__":
    main()
