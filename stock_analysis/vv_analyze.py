"""
大V雷达 - 视频分析模块
读取已转录视频，调用 DeepSeek 做四维分析（话题/选人逻辑/标的/空间），
写入 vv_videos.analysis_json + vv_analysis 表

用法:
  python vv_analyze.py                    # 分析所有未分析视频（上限20）
  python vv_analyze.py --vv yanbao60      # 分析指定大V
  python vv_analyze.py --limit 10         # 只分析前N个
  python vv_analyze.py --days 1           # 只分析最近N天的
  python vv_analyze.py --all              # 无视上限，全量分析
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from config import DEEPSEEK_API_KEY

DATA_DIR = Path("D:/1989n/stock_data")
DB_PATH = DATA_DIR / "vv_radar.db"
TZ_SH = timezone(timedelta(hours=8))

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
REQUEST_TIMEOUT = 90

MAX_ANALYZE_BATCH = 20  # 单次默认上限

# 三V角色定义，用于交叉验证标注
VV_ROLES = {
    "yanbao60": "宏观/信息层级架构师",
    "guojame": "资金结构解码器",
    "85164940078": "供应链量化策略师",
    "Trader9": "行家/情绪+题材",
    "Cyclequeen": "行家/情绪周期",
    "HuDaMao.New": "行家/技术形态",
    "xiaositv": "行家/宏观",
}

ANALYSIS_PROMPT = """你是一位交易信号分析师。分析以下抖音投资大V的视频转录内容，提取交易信号。

大V抖音号: {vv_id}
大V昵称: {vv_name}

视频描述: {desc}

转录内容:
{transcript}

请分析并返回 JSON 格式（只输出JSON，不要其他文字）：
{{
  "topics": ["涉及话题1", "涉及话题2", ...],
  "logic_why": "该大V的核心观点/选股逻辑（1-3句话）",
  "tickers": ["股票代码或名称", ...],
  "upside_analysis": "空间判断（如果有）",
  "confidence": "high/medium/low",
  "key_signals": ["关键信号1", "关键信号2", ...]
}}
"""


def get_unanalyzed(vv_id=None, limit=None, days=None, all_mode=False):
    """获取已转录但未分析的视频"""
    max_rows = limit if limit else (None if all_mode else MAX_ANALYZE_BATCH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT v.aweme_id, v.vv_id, v.desc, v.create_time, v.duration,
               v.transcript_text, f.name as vv_name
        FROM vv_videos v
        LEFT JOIN vv_follows f ON v.vv_id = f.id
        WHERE v.transcript_text IS NOT NULL
          AND v.transcript_text != ''
          AND (v.analysis_json IS NULL OR v.analysis_json = '')
    """
    params = []
    if vv_id:
        query += " AND v.vv_id = ?"
        params.append(vv_id)
    if days is not None:
        cutoff = int((datetime.now(TZ_SH) - timedelta(days=days)).timestamp())
        query += " AND v.create_time >= ?"
        params.append(cutoff)

    query += " ORDER BY v.create_time DESC"

    if max_rows:
        query += f" LIMIT {max_rows}"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def analyze_with_deepseek(transcript, vv_id, vv_name, desc):
    """调用 DeepSeek 分析单条转录"""
    if not DEEPSEEK_API_KEY:
        print("  [SKIP] DEEPSEEK_API_KEY 未配置")
        return None

    prompt = ANALYSIS_PROMPT.format(
        transcript=transcript[:3000],  # 截断避免超 token
        vv_id=vv_id,
        vv_name=vv_name or vv_id,
        desc=(desc or "")[:200],
    )

    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个交易信号分析师。输出严格JSON，不要markdown。不要使用股票代码"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]

        # 剥离可能的 markdown 围栏
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        print(f"  [WARN] DeepSeek 返回非JSON，原始内容: {content[:200]}")
        return None
    except Exception as e:
        print(f"  [ERROR] DeepSeek 调用失败: {e}")
        return None


def save_analysis(aweme_id, vv_id, vv_name, result):
    """保存分析结果到 vv_videos.analysis_json + vv_analysis 表"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    analysis_json = json.dumps(result, ensure_ascii=False)

    # 更新 vv_videos 表的 analysis_json 字段
    c.execute(
        "UPDATE vv_videos SET analysis_json = ? WHERE aweme_id = ?",
        (analysis_json, aweme_id),
    )

    # 写入 vv_analysis 表
    c.execute(
        """INSERT OR REPLACE INTO vv_analysis
           (aweme_id, vv_id, vv_name, topics, logic_why, tickers,
            upside_analysis, confidence, raw_response, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aweme_id,
            vv_id,
            vv_name or vv_id,
            json.dumps(result.get("topics", []), ensure_ascii=False),
            result.get("logic_why", ""),
            json.dumps(result.get("tickers", []), ensure_ascii=False),
            result.get("upside_analysis", ""),
            result.get("confidence", "medium"),
            analysis_json,
            datetime.now(TZ_SH).isoformat(),
        ),
    )

    conn.commit()
    conn.close()


def run_analysis(vv_id=None, limit=None, days=None, all_mode=False):
    """执行批量分析"""
    videos = get_unanalyzed(vv_id, limit, days, all_mode)
    if not videos:
        print("没有待分析的视频（所有已转录视频均已分析）")
        return []

    print(f"待分析: {len(videos)} 个视频\n")
    results = []

    for i, v in enumerate(videos):
        aweme_id = v["aweme_id"]
        vid = v["vv_id"]
        name = v.get("vv_name") or vid
        desc = (v["desc"] or "")[:60]
        transcript = v["transcript_text"] or ""

        if not transcript.strip():
            print(f"[{i+1}/{len(videos)}] {vid} | {desc} -> 跳过（无转录内容）")
            continue

        print(f"[{i+1}/{len(videos)}] {vid} | {desc}")

        result = analyze_with_deepseek(transcript, vid, name, v["desc"])
        if result:
            save_analysis(aweme_id, vid, name, result)
            confidence = result.get("confidence", "?")
            topics = ", ".join(result.get("topics", [])[:3])
            print(f"  -> {confidence} | {topics}")
            results.append({"aweme_id": aweme_id, "vv_id": vid, "result": result})
        else:
            print(f"  -> 分析失败")

    print(f"\n分析完成: {len(results)}/{len(videos)} 成功")
    return results


def build_daily_digest():
    """从今日已分析视频构建三V互补日报摘要"""
    today_start = datetime.now(TZ_SH).replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = int(today_start.timestamp())

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 获取今日已分析视频
    c.execute("""
        SELECT vv_id, vv_name, topics, logic_why, tickers, upside_analysis, confidence,
               analyzed_at
        FROM vv_analysis
        WHERE analyzed_at >= ?
        ORDER BY vv_id, analyzed_at DESC
    """, (today_start.isoformat(),))
    rows = [dict(r) for r in c.fetchall()]

    conn.close()
    return rows


def print_daily_digest():
    """打印三V互补日报"""
    digest = build_daily_digest()
    if not digest:
        print("今日暂无分析数据")
        return

    print(f"\n{'='*60}")
    print(f"大V雷达日报 {datetime.now(TZ_SH).strftime('%Y-%m-%d')}")
    print(f"{'='*60}")

    # 按大V分组
    by_vv = {}
    for d in digest:
        by_vv.setdefault(d["vv_id"], []).append(d)

    for vv_id, items in by_vv.items():
        role = VV_ROLES.get(vv_id, "")
        name = items[0].get("vv_name", vv_id)
        print(f"\n--- {name} (@{vv_id}) {f'[{role}]' if role else ''} ---")
        for item in items:
            topics = item["topics"] or "[]"
            if isinstance(topics, str):
                try:
                    topics = json.loads(topics)
                except (json.JSONDecodeError, TypeError):
                    topics = [topics]
            confidence = item.get("confidence", "?")
            logic = (item.get("logic_why") or "")[:100]
            print(f"  [{confidence}] {', '.join(topics[:3])}")
            if logic:
                print(f"    逻辑: {logic}")

    # 三V交叉验证
    v3_ids = ["yanbao60", "guojame", "85164940078"]
    v3_present = [vid for vid in v3_ids if vid in by_vv]
    if len(v3_present) >= 2:
        print(f"\n--- 三V互补交叉验证 ---")
        for vid in v3_present:
            items = by_vv[vid]
            role = VV_ROLES.get(vid, "")
            logics = [i.get("logic_why", "")[:80] for i in items if i.get("logic_why")]
            print(f"  {role}(@{vid}): {' | '.join(logics)}")
    elif v3_present:
        print(f"\n--- 今日仅 {v3_present[0]} 有更新，三V不完整 ---")

    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="大V雷达 - 视频分析")
    parser.add_argument("--vv", help="只分析指定大V")
    parser.add_argument("--limit", type=int, help=f"分析数量上限（默认{MAX_ANALYZE_BATCH}）")
    parser.add_argument("--days", type=int, help="只分析最近N天")
    parser.add_argument("--all", action="store_true", help="全量分析无视上限")
    parser.add_argument("--digest", action="store_true", help="只输出今日日报")
    args = parser.parse_args()

    if args.digest:
        print_daily_digest()
    else:
        run_analysis(args.vv, args.limit, args.days, args.all)
        print_daily_digest()
