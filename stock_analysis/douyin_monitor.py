"""
douyin_monitor.py — 抖音博主监控管线

每日自动扫描 3 位指定博主的最新视频：
  1. 拉取主页最新视频列表
  2. 对比历史，识别新增视频
  3. 提取内容（作者/sec_uid/统计）
  4. 关键字价值评估 (HIGH/MEDIUM/LOW)
  5. 写入监控日报

用法:
  python douyin_monitor.py              # 全量扫描
  python douyin_monitor.py --report     # 只看今日报告
  python douyin_monitor.py --history    # 看历史状态
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from douyin_extractor import extract_video, get_profile_video_ids, OUTPUT_DIR

logger = logging.getLogger("douyin_monitor")

CREATORS_FILE = OUTPUT_DIR / "creators.json"
MONITOR_DIR = OUTPUT_DIR / "monitor"
HISTORY_FILE = MONITOR_DIR / "history.json"

MONITOR_DIR.mkdir(parents=True, exist_ok=True)


# ── 历史管理 ──


def _load_history() -> dict:
    """加载已处理视频 ID 记录 {creator_label: [vid, ...]}"""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("历史文件损坏，重置")
    return {}


def _save_history(history: dict):
    """保存已处理视频 ID 记录"""
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 价值评估 ──


def _assess_video(result: dict, creator_cfg: dict) -> dict:
    """基于关键字匹配评估视频价值。

    HIGH:  匹配 3+ 个关注关键字 — 直接相关
    MEDIUM: 匹配 1-2 个关键字 — 部分相关
    LOW:   无关键字匹配 — 不相关
    """
    text = (
        (result.get("title", "") or "") + " " +
        (result.get("description", "") or "") + " " +
        (result.get("chapter_content", "") or "") + " " +
        (result.get("caption", "") or "")
    ).lower()

    keywords = creator_cfg.get("high_value_keywords", [])
    matched = [kw for kw in keywords if kw.lower() in text]
    match_count = len(matched)

    if match_count >= 3:
        tier = "HIGH"
    elif match_count >= 1:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return {
        "tier": tier,
        "score": match_count,
        "matched_keywords": matched,
    }


# ── 价值摘要（摘要英文避免中文乱码） ──


_TIER_EMOJI = {"HIGH": "★★★", "MEDIUM": "★★", "LOW": "★"}
_TIER_LABEL = {"HIGH": "高价值", "MEDIUM": "中价值", "LOW": "低价值"}


# ── 主扫描 ──


def run_monitor(max_new_per_creator: int = 3) -> list[dict]:
    """执行一次全量监控扫描。

    Args:
        max_new_per_creator: 每个博主最多提取的新视频数（按主页出现顺序取最新）

    Returns:
        本次新增的视频分析结果列表
    """
    raw = json.loads(CREATORS_FILE.read_text(encoding="utf-8"))
    history = _load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    new_findings = []

    # 扁平化：提取所有分类下的博主，跳过 _meta
    creators = {}
    for _cat, members in raw.items():
        if _cat.startswith("_"):
            continue
        if isinstance(members, dict):
            creators.update(members)

    for creator_label, cfg in creators.items():
        sec_uid = cfg.get("sec_uid")
        if not sec_uid:
            logger.info("跳过 %s: 无 sec_uid", creator_label)
            continue
        logger.info("扫描博主: %s", creator_label)

        # 获取主页视频 ID
        vids = get_profile_video_ids(sec_uid, max_scroll=2)

        # 获取历史记录（去重用）
        seen = set(history.get(creator_label, []))
        new_vids = [v for v in vids if v not in seen]
        # 只处理前 N 个最新视频
        new_vids = new_vids[:max_new_per_creator]

        if not new_vids:
            logger.info("  %s: 无新增视频", creator_label)
            continue

        logger.info("  %s: %d 个新增视频", creator_label, len(new_vids))

        for vid in new_vids:
            video_url = f"https://www.douyin.com/video/{vid}"
            logger.info("  提取: %s", video_url)

            result = extract_video(video_url)

            # 评估价值
            assessment = _assess_video(result, cfg)
            result["assessment"] = assessment
            result["creator_label"] = creator_label
            result["scanned_at"] = today

            new_findings.append(result)

            # 保存每条视频的提取结果
            out_file = OUTPUT_DIR / f"douyin_{vid}.json"
            out_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 更新历史
        history[creator_label] = list(seen | set(new_vids))

    # 保存历史
    _save_history(history)

    return new_findings


# ── 报告生成 ──


def _format_findings(findings: list[dict]) -> str:
    """生成可读的监控报告文本"""
    if not findings:
        return "今日暂无新增视频。"

    lines = [f"监控报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
             f"新增视频: {len(findings)} 条\n"]

    # 按价值排序：HIGH → MEDIUM → LOW
    tier_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings.sort(key=lambda r: tier_order.get(r.get("assessment", {}).get("tier", "LOW"), 99))

    for r in findings:
        assess = r.get("assessment", {})
        tier = assess.get("tier", "LOW")
        emoji = _TIER_EMOJI.get(tier, "★")
        label = _TIER_LABEL.get(tier, "未知")
        title = (r.get("title", "") or "")[:80]
        author = r.get("author", "?")
        stats = r.get("stats", {})
        keywords = assess.get("matched_keywords", [])

        # 用 --- 分隔视频条目
        lines.append(f"{emoji} [{label}] {author}")
        lines.append(f"  标题: {title}")
        lines.append(f"  URL:  https://www.douyin.com/video/{r.get('video_id', '')}")
        lines.append(f"  统计: 👍{stats.get('digg_count','?')} 💬{stats.get('comment_count','?')} 🔄{stats.get('share_count','?')}")
        if keywords:
            lines.append(f"  命中: {', '.join(keywords)}")
        chapter = r.get("chapter_content", "") or ""
        if chapter:
            lines.append(f"  内容: {chapter[:150]}")
        lines.append("")

    return "\n".join(lines)


# ── CLI ──


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:]

    if args and args[0] == "--report":
        # 查看今日报告
        today = datetime.now().strftime("%Y-%m-%d")
        report_file = MONITOR_DIR / f"report_{today}.json"
        if report_file.exists():
            findings = json.loads(report_file.read_text(encoding="utf-8"))
            print(_format_findings(findings))
        else:
            print(f"今日报告不存在: {report_file}")
        sys.exit(0)

    if args and args[0] == "--history":
        # 查看历史状态
        history = _load_history()
        if not history:
            print("尚无监控历史")
            sys.exit(0)
        print("监控历史状态:")
        for creator, vids in history.items():
            print(f"  {creator}: {len(vids)} 个视频已处理")
        sys.exit(0)

    # 执行扫描
    print(f"\n开始监控扫描: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    findings = run_monitor()

    # 生成报告
    report_text = _format_findings(findings)

    # 写入日报
    today = datetime.now().strftime("%Y-%m-%d")
    report_file = MONITOR_DIR / f"report_{today}.json"
    report_file.write_text(
        json.dumps(findings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_file.with_suffix(".txt").write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"\n日报已保存: {report_file}")

    return findings


if __name__ == "__main__":
    main()
