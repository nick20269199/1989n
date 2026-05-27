"""
douyin_archive.py — 抖音博主全量归档扫描器

通过 /aweme/v1/web/aweme/post/ API 批量拉取博主全部视频的章节数据，
一次性获取所有视频的描述、章节内容、统计信息。

用法:
  python douyin_archive.py <nickname> <sec_uid>    # 扫描单个博主
  python douyin_archive.py --all                   # 扫描 creators.json 中所有博主
  python douyin_archive.py --list                  # 查看已归档
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger("douyin_archive")

OUTPUT_DIR = Path("D:/1989n/stock_data/douyin")
CREATORS_FILE = OUTPUT_DIR / "creators.json"
COOKIES_FILE = OUTPUT_DIR / "cookies.json"
ARCHIVE_DIR = OUTPUT_DIR / "archive"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# 每页数量
PAGE_SIZE = 20
# 最大页数（安全限制，防止拉取过多）
MAX_PAGES = 50


def scan_creator(sec_uid: str, nickname: str = "", max_pages: int = MAX_PAGES) -> list[dict]:
    """批量拉取某个博主的所有视频章节数据。

    通过 /aweme/v1/web/aweme/post/ 接口分页获取，一次性提取：
    - desc（描述）
    - chapter_list / chapter_abstract（章节内容——视频实际讲的什么）
    - caption（字幕）
    - statistics（统计数据）
    - create_time（发布时间）

    Args:
        sec_uid: 博主的 sec_uid
        nickname: 博主昵称（仅用于日志）
        max_pages: 最大拉取页数（每页20条）

    Returns:
        视频数据列表，按发布时间降序
    """
    all_videos = []
    cursor = "0"
    page_count = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            storage_state=str(COOKIES_FILE) if COOKIES_FILE.exists() else None,
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        page = context.new_page()

        try:
            # 先访问首页初始化 session
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            logger.info("session 初始化完成，开始拉取 %s 的视频列表", nickname or sec_uid[:30])

            while page_count < max_pages:
                result = page.evaluate("""
                    async (args) => {
                        const params = new URLSearchParams({
                            device_platform: 'webapp',
                            aid: '6383',
                            channel: 'channel_pc_web',
                            sec_user_id: args.sec_uid,
                            max_cursor: args.cursor,
                            count: '20',
                            publish_video_strategy_type: '2',
                        });
                        const resp = await fetch('/aweme/v1/web/aweme/post/?' + params.toString());
                        const data = await resp.json();
                        return JSON.stringify(data);
                    }
                """, {"sec_uid": sec_uid, "cursor": cursor})

                data = json.loads(result)
                aweme_list = data.get("aweme_list", [])
                if not aweme_list:
                    logger.info("  无更多视频")
                    break

                for aweme in aweme_list:
                    chapter_list = aweme.get("chapter_list") or []
                    chapter_abstract = aweme.get("chapter_abstract") or ""
                    chapter_parts = []
                    for ch in chapter_list[:50]:
                        detail = ch.get("detail", "") or ""
                        if detail:
                            chapter_parts.append(detail)
                    chapter_content = chapter_abstract or " | ".join(chapter_parts) or ""

                    stats = aweme.get("statistics", {})
                    caption = aweme.get("caption") or ""
                    desc = aweme.get("desc") or ""

                    all_videos.append({
                        "aweme_id": aweme.get("aweme_id", ""),
                        "desc": desc[:2000],
                        "caption": caption[:500],
                        "chapter_content": chapter_content[:2000],
                        "chapter_list": [
                            {"desc": ch.get("desc", ""), "detail": (ch.get("detail", "") or "")[:300],
                             "timestamp": ch.get("timestamp", 0)}
                            for ch in chapter_list[:20]
                        ],
                        "has_chapters": bool(chapter_content),
                        "create_time": aweme.get("create_time", 0),
                        "duration": (aweme.get("video") or {}).get("duration", 0),
                        "stats": {
                            "digg_count": stats.get("digg_count", 0),
                            "comment_count": stats.get("comment_count", 0),
                            "share_count": stats.get("share_count", 0),
                            "collect_count": stats.get("collect_count", 0),
                        },
                    })

                has_more = data.get("has_more", 0)
                cursor = str(data.get("max_cursor", 0))
                page_count += 1
                logger.info("  第%d页: %d条 (共%d条, has_more=%s)",
                           page_count, len(aweme_list), len(all_videos), has_more)

                if not has_more:
                    logger.info("  全部拉取完成")
                    break

                page.wait_for_timeout(500)  # 避免触发限流

        except Exception as e:
            logger.exception("归档扫描异常")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return all_videos


def scan_all_creators():
    """扫描 creators.json 中所有有 sec_uid 的博主。"""
    creators_raw = json.loads(CREATORS_FILE.read_text(encoding="utf-8"))
    # 扁平化
    creators = {}
    for cat, members in creators_raw.items():
        if cat.startswith("_"):
            continue
        if isinstance(members, dict):
            creators.update(members)

    total_videos = 0
    for name, cfg in creators.items():
        sec_uid = cfg.get("sec_uid")
        if not sec_uid:
            logger.info("跳过 %s: 无 sec_uid", name)
            continue

        logger.info("=" * 50)
        logger.info("归档: %s", name)
        videos = scan_creator(sec_uid, nickname=name)
        if not videos:
            logger.warning("  %s: 未获取到视频", name)
            continue

        # 保存归档
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
        archive_file = ARCHIVE_DIR / f"{safe_name}.json"
        archive_data = {
            "nickname": name,
            "sec_uid": sec_uid,
            "scanned_at": datetime.now().isoformat(),
            "total_videos": len(videos),
            "videos_with_chapters": sum(1 for v in videos if v.get("has_chapters")),
            "videos": videos,
        }
        archive_file.write_text(
            json.dumps(archive_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("  ✅ 已保存: %s (%d条视频, %d条有章节数据)",
                    archive_file, len(videos), archive_data["videos_with_chapters"])
        total_videos += len(videos)

    logger.info("=" * 50)
    logger.info("全部归档完成: 共 %d 条视频", total_videos)


def list_archives():
    """查看已归档博主列表。"""
    if not ARCHIVE_DIR.exists():
        print("暂无归档数据")
        return
    archives = sorted(ARCHIVE_DIR.glob("*.json"))
    if not archives:
        print("暂无归档数据")
        return
    print(f"已归档博主 ({len(archives)}):")
    for fp in archives:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            total = data.get("total_videos", 0)
            with_ch = data.get("videos_with_chapters", 0)
            scanned = data.get("scanned_at", "")[:10]
            print(f"  {data['nickname']}: {total}条视频 ({with_ch}条有章节) 归档于{scanned}")
        except Exception:
            print(f"  {fp.name}: (读取失败)")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:]

    if not args or args[0] == "--list":
        list_archives()
        sys.exit(0)

    if args[0] == "--all":
        scan_all_creators()
        sys.exit(0)

    # 单个博主: python douyin_archive.py <nickname> <sec_uid>
    if len(args) >= 2:
        nickname = args[0]
        sec_uid = args[1]
        max_pages = int(args[2]) if len(args) > 2 else MAX_PAGES
        print(f"扫描博主: {nickname} (最多{max_pages}页)")
        videos = scan_creator(sec_uid, nickname=nickname, max_pages=max_pages)
        print(f"共获取 {len(videos)} 条视频")
        with_ch = sum(1 for v in videos if v.get("has_chapters"))
        print(f"其中 {with_ch} 条有章节数据")

        safe_name = re.sub(r'[\\/:*?"<>|]', "_", nickname)
        archive_file = ARCHIVE_DIR / f"{safe_name}.json"
        archive_data = {
            "nickname": nickname,
            "sec_uid": sec_uid,
            "scanned_at": datetime.now().isoformat(),
            "total_videos": len(videos),
            "videos_with_chapters": with_ch,
            "videos": videos,
        }
        archive_file.write_text(
            json.dumps(archive_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已保存: {archive_file}")
        sys.exit(0)

    print("用法:")
    print("  python douyin_archive.py <nickname> <sec_uid>  # 扫描单个博主")
    print("  python douyin_archive.py --all                  # 扫描全部")
    print("  python douyin_archive.py --list                 # 查看已归档")
    sys.exit(1)


if __name__ == "__main__":
    main()
