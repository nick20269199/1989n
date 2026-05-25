"""
大V雷达 - 每日全自动管线
编排: 转录 → 分析 → 日报 → 推送

用法:
  python vv_daily.py                     # 标准日运行（转录15个 + 分析 + 日报）
  python vv_daily.py --transcribe-only   # 只转录
  python vv_daily.py --analyze-only      # 只分析
  python vv_daily.py --digest-only       # 只出日报
  python vv_daily.py --full             # 全量转录（无视上限）
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 路径
STOCK_DIR = Path("D:/1989n/stock_analysis")
DATA_DIR = Path("D:/1989n/stock_data")
PYTHON = "D:/Python314/python"

TZ_SH = timezone(timedelta(hours=8))

# 默认转录上限（单次）
DEFAULT_TRANSCRIBE_LIMIT = 15


def log(msg):
    ts = datetime.now(TZ_SH).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run_step(cmd, desc):
    """执行一个步骤并返回 exit code"""
    log(f"{desc}...")
    start = time.time()
    result = subprocess.run(cmd, capture_output=False, text=True)
    elapsed = time.time() - start
    if result.returncode == 0:
        log(f"{desc} 完成 ({elapsed:.1f}s)")
    else:
        log(f"{desc} 失败 (exit={result.returncode}, {elapsed:.1f}s)")
    return result.returncode


def step_transcribe(limit=DEFAULT_TRANSCRIBE_LIMIT, full=False):
    """Step 1: 转录积压视频（优先级排序）"""
    cmd = [PYTHON, "vv_transcribe.py", "--priority"]
    if full:
        cmd.append("--limit")
        cmd.append("999")
    else:
        cmd.append("--limit")
        cmd.append(str(limit))
    return run_step(cmd, f"转录 (上限{limit if not full else '全量'})")


def step_analyze(days=2):
    """Step 2: 分析新转录的视频"""
    # 先分析今天/昨天的
    cmd = [PYTHON, "vv_analyze.py", "--days", str(days)]
    rc1 = run_step(cmd, f"分析 (最近{days}天)")
    # 再补分析剩余积压（上限20）
    cmd2 = [PYTHON, "vv_analyze.py", "--limit", "20"]
    rc2 = run_step(cmd2, "分析 (补充积压)")
    return rc1 if rc1 != 0 else rc2


def step_digest():
    """Step 3: 生成日报"""
    cmd = [PYTHON, "vv_analyze.py", "--digest"]
    return run_step(cmd, "日报生成")


def step_push():
    """Step 4: 推送日报到飞书"""
    log("推送日报到飞书...")
    # 先通过 digest 获取文本
    result = subprocess.run(
        [PYTHON, "-c", """
import sys; sys.path.insert(0, r'D:/1989n/stock_analysis')
import json
from vv_analyze import build_daily_digest, VV_ROLES

digest = build_daily_digest()
if not digest:
    print("NO_DATA")
    sys.exit(0)

lines = [f"【大V雷达日报 {__import__('datetime').datetime.now().__import__('pytz').timezone('Asia/Shanghai').strftime('%m-%d')}】"]
by_vv = {}
for d in digest:
    by_vv.setdefault(d['vv_id'], []).append(d)

for vv_id, items in by_vv.items():
    role = VV_ROLES.get(vv_id, '')
    name = items[0].get('vv_name', vv_id) or vv_id
    header = f"{name}" + (f" [{role}]" if role else "")
    for item in items[:2]:
        topics = item['topics'] or '[]'
        if isinstance(topics, str):
            try: topics = json.loads(topics)
            except: topics = [topics]
        c = item.get('confidence', '?')
        t = ', '.join(topics[:2]) if topics else '(无话题)'
        logic = (item.get('logic_why') or '')[:80]
        lines.append(f"  [{c}] {t}")
        if logic: lines.append(f"     {logic}")

text = chr(10).join(lines)
print(text)
"""],
        capture_output=True, text=True, timeout=30,
    )

    report_text = result.stdout.strip()
    if report_text == "NO_DATA":
        log("  今日无分析数据，跳过推送")
        return 0

    # 推送到飞书 alerts 群
    push_cmd = [
        PYTHON, "-c", f"""
import sys; sys.path.insert(0, r'D:/1989n/stock_analysis')
import feishu_sender
text = {json.dumps(report_text)}
feishu_sender.send_text_message('【大V雷达】', text)
print('推送完成')
"""
    ]
    rc = subprocess.run(push_cmd, timeout=30)
    log(f"推送 {'成功' if rc.returncode == 0 else '失败'}")
    return rc.returncode


def main():
    import argparse
    parser = argparse.ArgumentParser(description="大V雷达 - 每日全自动管线")
    parser.add_argument("--transcribe-only", action="store_true", help="只转录")
    parser.add_argument("--analyze-only", action="store_true", help="只分析")
    parser.add_argument("--digest-only", action="store_true", help="只出日报")
    parser.add_argument("--full", action="store_true", help="全量转录")
    parser.add_argument("--no-push", action="store_true", help="不推送飞书")
    parser.add_argument("--limit", type=int, help=f"转录数量上限（默认{DEFAULT_TRANSCRIBE_LIMIT}）")
    args = parser.parse_args()

    log("大V雷达每日管线启动")
    start = time.time()

    if args.transcribe_only:
        step_transcribe(full=args.full, limit=args.limit or DEFAULT_TRANSCRIBE_LIMIT)
    elif args.analyze_only:
        step_analyze(days=7)
    elif args.digest_only:
        step_digest()
    else:
        # 标准流程
        batch = args.limit or DEFAULT_TRANSCRIBE_LIMIT
        step_transcribe(batch if not args.full else 999, args.full)
        step_analyze()
        step_digest()
        if not args.no_push:
            step_push()

    elapsed = time.time() - start
    log(f"管线总耗时: {elapsed/60:.1f} 分钟")


if __name__ == "__main__":
    main()
