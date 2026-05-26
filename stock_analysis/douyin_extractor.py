"""
douyin_extractor.py — 抖音内容提取器

用 Playwright 绕过反爬，提取视频页面文本内容（标题/描述/作者/统计）。
不做视频下载，只取文字信息供分析。

用法:
  python douyin_extractor.py <url>
  python douyin_extractor.py --file urls.txt

依赖: playwright (pip install playwright)
"""

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger("douyin_extractor")

OUTPUT_DIR = Path("D:/1989n/stock_data/douyin")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── 核心提取 ──


def extract_video(url: str, timeout: int = 30000) -> dict:
    """提取单条抖音视频的文字内容。

    Returns:
        {
            "url": str,
            "success": bool,
            "title": str,
            "description": str,
            "author": str,
            "author_id": str,
            "stats": {"likes": str, "comments": str, "shares": str},
            "video_id": str,
            "page_text_snippet": str,  # 前2000字
            "error": str,
        }
    """
    vid = _extract_video_id(url)
    result = {
        "url": url,
        "video_id": vid or "",
        "success": False,
        "title": "",
        "description": "",
        "author": "",
        "author_id": "",
        "stats": {},
        "page_text_snippet": "",
        "error": "",
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            # 用持久化缓存目录复用会话
            storage_state=OUTPUT_DIR / "cookies.json" if (OUTPUT_DIR / "cookies.json").exists() else None,
        )
        # 反检测注入
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh'],
            });
            // 覆盖chrome属性检测
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()

        try:
            logger.info("导航到: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            # 等页面稳定（JS渲染+可能的反爬挑战）
            page.wait_for_timeout(5000)

            # 检测是否被反爬拦截（宽松模式：只要有关键内容就算成功）
            page_title = page.title()
            body_text = page.inner_text("body")[:10000] if page.query_selector("body") else ""

            # 先看有没有实质性内容（视频标题/描述）
            has_content = bool(
                re.search(r'(?:video|aweme|item_ids|desc).{0,100}', body_text, re.IGNORECASE)
                or any(kw in body_text for kw in ["点赞", "评论", "分享", "关注"])
            )
            is_hard_blocked = _is_blocked(body_text, page_title)

            if is_hard_blocked and not has_content:
                result["error"] = "被反爬拦截"
                result["page_text_snippet"] = body_text[:500]
                browser.close()
                return result

            # ── 提取各字段 ──

            # 视频标题/描述（抖音页面描述通常在 <meta> 或 .desc 里）
            desc = _safe_extract(page, [
                "meta[name='description']",
                ".video-info .desc",
                ".desc",
                "[data-testid='desc']",
                ".video-detail",
            ], attr="content")
            if not desc:
                # 从 meta description 提取
                meta_desc = _safe_extract(page, ["meta[name='description']"], attr="content")
                if meta_desc:
                    desc = meta_desc

            # 作者名
            author = _safe_extract(page, [
                ".author-name",
                ".nickname",
                "[data-testid='author']",
                ".author-info .name",
            ])
            # CSS 选择器未命中时从 body_text 正则回退
            if not author:
                m = re.search(r'([一-鿿]{2,8})\s*\n+\s*粉丝\d+', body_text)
                if m:
                    author = m.group(1)

            # 作者ID（从URL或其他地方）
            author_id = ""
            author_link = _safe_extract(page, [".author-link"], attr="href")
            if author_link and "/user/" in author_link:
                author_id = author_link.split("/user/")[-1].split("?")[0]

            # 互动数据 (CSS + body_text 正则回退)
            stats = {}
            stat_labels = page.query_selector_all(".stat-item, .count, .engage-count")
            for el in stat_labels:
                text = el.inner_text().strip()
                if "赞" in text or re.match(r"^\d+", text):
                    stats["likes"] = text
                elif "评" in text:
                    stats["comments"] = text
                elif "分享" in text or "转" in text:
                    stats["shares"] = text
            if not stats:
                like_m = re.search(r'(?:点赞|获赞|喜欢)\s*(\d[\d.]*[万wW]?)', body_text)
                if like_m:
                    stats["likes"] = like_m.group(1)
                comment_m = re.search(r'评论\s*(\d[\d.]*[万wW]?)', body_text)
                if comment_m:
                    stats["comments"] = comment_m.group(1)
                share_m = re.search(r'分享\s*(\d[\d.]*[万wW]?)', body_text)
                if share_m:
                    stats["shares"] = share_m.group(1)
                if not stats.get("likes"):
                    fl_m = re.search(r'粉丝\d+.*?获赞(\d+)', body_text)
                    if fl_m:
                        stats["likes"] = fl_m.group(1)

            result.update({
                "success": True,
                "title": page_title,
                "description": (desc or "")[:2000],
                "author": (author or "")[:100],
                "author_id": author_id[:100],
                "stats": stats,
                "page_text_snippet": body_text[:2000],
            })
            logger.info("提取成功: %s | 作者=%s | desc=%s...", vid, author, (desc or "")[:80])

        except PWTimeout:
            result["error"] = "页面加载超时"
        except Exception as e:
            result["error"] = f"提取异常: {e}"
            logger.exception("提取失败 %s", url)
        finally:
            try:
                browser.close()
            except:
                pass

    return result


def extract_multiple(urls: list[str], max_workers: int = 3) -> list[dict]:
    """批量提取多条视频。串行执行（避免被识别为爬虫）。"""
    results = []
    for i, url in enumerate(urls):
        logger.info("[%d/%d] 处理 %s", i + 1, len(urls), url)
        r = extract_video(url)
        results.append(r)
        # 每条间隔3-5秒
        if i < len(urls) - 1:
            time.sleep(3)
    return results


# ── 辅助 ──


def _extract_video_id(url: str) -> Optional[str]:
    """从 URL 提取视频ID。"""
    m = re.search(r"video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19})", url)
    if m:
        return m.group(1)
    return None


def _safe_extract(page, selectors: list[str], attr: str = "inner_text") -> str:
    """依次尝试多个选择器，返回第一个匹配的文本。"""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                if attr == "inner_text":
                    text = el.inner_text()
                elif attr == "content":
                    text = el.get_attribute("content") or ""
                else:
                    text = el.get_attribute(attr) or ""
                if text and text.strip():
                    return text.strip()
        except Exception:
            continue
    return ""


def _is_blocked(body_text: str, title: str = "") -> bool:
    """检测页面是否被反爬拦截。"""
    indicators = [
        "验证", "captcha", "cf-challenge", "challenge-platform",
        "检测到异常", "访问被拒绝", "Please stand by",
        "just a moment", "Checking your browser",
        "安全验证", "人机验证",
    ]
    for ind in indicators:
        if ind in body_text.lower() or ind in title:
            return True
    return False


# ── CLI ──


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:]

    urls = []
    if not args:
        print("用法:")
        print("  python douyin_extractor.py <抖音视频URL>")
        print("  python douyin_extractor.py --file urls.txt")
        sys.exit(1)

    if args[0] == "--file":
        fp = Path(args[1])
        if not fp.exists():
            print(f"文件不存在: {fp}")
            sys.exit(1)
        urls = [line.strip() for line in fp.read_text().splitlines() if line.strip()]
    else:
        urls = [args[0]]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for url in urls:
        print(f"\n{'='*60}")
        print(f"提取: {url}")
        result = extract_video(url)

        out_file = OUTPUT_DIR / f"douyin_{_extract_video_id(url) or 'unknown'}.json"
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已保存: {out_file}")

        if result["success"]:
            print(f"  标题: {result['title']}")
            print(f"  作者: {result['author']}")
            print(f"  描述: {result['description'][:200]}")
            print(f"  互动: {result['stats']}")
        else:
            print(f"  ❌ 失败: {result['error']}")


if __name__ == "__main__":
    main()
