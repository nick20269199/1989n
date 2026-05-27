"""
douyin_extractor.py — 抖音内容提取器

用 Playwright 绕过反爬，提取视频页面文本内容。
自动解析短链接，自动复用桌面 APP 登录 session。
通过拦截 aweme API 获取作者 sec_uid 和准确统计数据。

用法:
  python douyin_extractor.py <url>
  python douyin_extractor.py --file urls.txt
  python douyin_extractor.py --profile <sec_uid>

依赖: playwright requests (pip install playwright requests)
"""

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger("douyin_extractor")

OUTPUT_DIR = Path("D:/1989n/stock_data/douyin")
COOKIES_FILE = OUTPUT_DIR / "cookies.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── URL 解析 ──


def _resolve_short_url(url: str) -> str:
    """解析抖音短链接 (v.douyin.com/xxx) 为完整 URL。"""
    if "v.douyin.com" not in url:
        return url
    try:
        r = requests.get(
            url,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        return r.url
    except Exception as e:
        logger.warning("短链接解析失败 %s: %s", url, e)
        return url


def _extract_video_id(url: str) -> Optional[str]:
    """从 URL 提取视频ID。"""
    url = _resolve_short_url(url)
    m = re.search(r"video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19})", url)
    if m:
        return m.group(1)
    return None


# ── Playwright 上下文工厂 ──


def _create_browser_context(pw, headless: bool = True):
    """创建配置了反检测和登录 session 的浏览器上下文。"""
    browser = pw.chromium.launch(
        headless=headless,
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
        storage_state=str(COOKIES_FILE) if COOKIES_FILE.exists() else None,
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh'],
        });
        window.chrome = { runtime: {} };
    """)
    return browser, context


# ── 核心提取 ──


def extract_video(url: str, timeout: int = 30000) -> dict:
    """提取单条抖音视频的文字内容。

    拦截 /aweme/v1/web/aweme/detail/ API 获取作者 sec_uid 和精确统计。
    失败时回退到页面文本正则提取。
    """
    url = _resolve_short_url(url)
    vid = _extract_video_id(url)
    result = {
        "url": url,
        "video_id": vid or "",
        "success": False,
        "title": "",
        "description": "",
        "author": "",
        "author_id": "",
        "sec_uid": "",
        "stats": {},          # 精确统计（来自 API）
        "stats_display": {},  # 展示用统计（正则回退）
        "page_text_snippet": "",
        "chapter_content": "",   # 章节摘要（视频实际内容）
        "chapter_list": [],       # 章节明细 [{desc, detail, timestamp}]
        "caption": "",            # 视频字幕/补充描述
        "error": "",
    }

    with sync_playwright() as pw:
        browser, context = _create_browser_context(pw)
        page = context.new_page()

        api_aweme = {}

        def _on_response(response):
            if "/aweme/v1/web/aweme/detail/" not in response.url:
                return
            try:
                data = response.json()
                aweme_detail = data.get("aweme_detail") or {}
                if aweme_detail.get("author"):
                    api_aweme.update(aweme_detail)
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            logger.info("导航到: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(6000)

            page_title = page.title()
            body_text = page.inner_text("body")[:15000] if page.query_selector("body") else ""
            is_hard_blocked = _is_blocked(body_text, page_title)

            # ── API 数据优先 ──
            if api_aweme:
                author = api_aweme.get("author", {})
                stats = api_aweme.get("statistics", {})
                desc = api_aweme.get("desc", "") or ""
                caption = api_aweme.get("caption", "") or ""

                # 提取章节内容（视频实际内容摘要）
                chapter_list = api_aweme.get("chapter_list") or []
                chapter_abstract = api_aweme.get("chapter_abstract") or ""
                chapter_parts = []
                for ch in chapter_list[:20]:
                    d = ch.get("detail", "") or ""
                    if d:
                        chapter_parts.append(d)
                chapter_content = chapter_abstract or " | ".join(chapter_parts) or ""

                result.update({
                    "success": True,
                    "title": page_title,
                    "description": desc[:2000],
                    "caption": caption[:500],
                    "chapter_content": chapter_content[:2000],
                    "chapter_list": chapter_list[:20],
                    "author": (author.get("nickname", "") or "")[:100],
                    "author_id": str(author.get("unique_id", "") or ""),
                    "sec_uid": (author.get("sec_uid", "") or ""),
                    "stats": {
                        "digg_count": stats.get("digg_count", 0),
                        "comment_count": stats.get("comment_count", 0),
                        "share_count": stats.get("share_count", 0),
                        "collect_count": stats.get("collect_count", 0),
                    },
                    "page_text_snippet": body_text[:2000],
                })
                logger.info("提取成功 [API]: %s | 作者=%s | sec_uid=%s",
                            vid, result["author"],
                            (result["sec_uid"][:30] if result["sec_uid"] else "N/A"))
                return result

            # ── 无 API 数据，尝试正则回退 ──
            if is_hard_blocked:
                result["error"] = "被反爬拦截"
                result["page_text_snippet"] = body_text[:500]
                return result

            has_content = bool(
                re.search(r"(?:video|aweme|item_ids|desc).{0,100}", body_text, re.IGNORECASE)
                or any(kw in body_text for kw in ["点赞", "评论", "分享", "关注"])
            )
            if not has_content:
                result["error"] = "页面无有效内容"
                result["page_text_snippet"] = body_text[:500]
                return result

            # 作者名（支持中文/英文/括号）
            author = _safe_extract(page, [
                ".author-name", ".nickname", "[data-testid='author']",
                ".author-info .name",
            ])
            if not author:
                m = re.search(
                    r"([一-鿿\w（）()]{2,20})\s*\n+\s*粉丝[\d.万wWkK]+",
                    body_text,
                )
                if m:
                    author = m.group(1)

            # 互动数据
            stats = {}
            like_m = re.search(r"(?:点赞|获赞|喜欢)\s*(\d[\d.]*[万wW]?)", body_text)
            if like_m:
                stats["likes"] = like_m.group(1)
            comment_m = re.search(r"评论\s*(\d[\d.]*[万wW]?)", body_text)
            if comment_m:
                stats["comments"] = comment_m.group(1)
            share_m = re.search(r"分享\s*(\d[\d.]*[万wW]?)", body_text)
            if share_m:
                stats["shares"] = share_m.group(1)
            if not stats.get("likes"):
                fl_m = re.search(r"粉丝\d+.*?获赞(\d+)", body_text)
                if fl_m:
                    stats["likes"] = fl_m.group(1)

            desc = _safe_extract(page, ["meta[name='description']"], attr="content")

            result.update({
                "success": True,
                "title": page_title,
                "description": (desc or "")[:2000],
                "author": (author or "")[:100],
                "sec_uid": "",
                "stats": {},
                "stats_display": stats,
                "page_text_snippet": body_text[:2000],
            })
            logger.info("提取成功 [正则]: %s | 作者=%s", vid, result["author"])

        except PWTimeout:
            result["error"] = "页面加载超时"
        except Exception as e:
            result["error"] = f"提取异常: {e}"
            logger.exception("提取失败 %s", url)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return result


def extract_multiple(urls: list[str], delay: int = 3) -> list[dict]:
    """批量提取多条视频。串行执行。"""
    results = []
    for i, url in enumerate(urls):
        logger.info("[%d/%d] 处理 %s", i + 1, len(urls), url)
        r = extract_video(url)
        results.append(r)
        if i < len(urls) - 1:
            time.sleep(delay)
    return results


def get_profile_video_ids(sec_uid: str, max_scroll: int = 3) -> list[str]:
    """获取用户主页的最新视频 ID 列表。

    Args:
        sec_uid: 用户的 sec_uid
        max_scroll: 滚动加载次数
    Returns:
        视频 ID 列表，按页面出现顺序去重
    """
    profile_url = f"https://www.douyin.com/user/{sec_uid}"
    video_ids = []

    with sync_playwright() as pw:
        browser, context = _create_browser_context(pw)
        page = context.new_page()

        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            for _ in range(max_scroll):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            content = page.content()
            ids = re.findall(r'video/(\d{19})', content)
            seen = set()
            for vid in ids:
                if vid not in seen:
                    seen.add(vid)
                    video_ids.append(vid)

            logger.info("用户主页获取到 %d 个视频", len(video_ids))
        except Exception as e:
            logger.exception("获取用户主页视频失败")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return video_ids


# ── 辅助 ──


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

    if not args:
        print("用法:")
        print("  python douyin_extractor.py <抖音视频URL>")
        print("  python douyin_extractor.py --file urls.txt")
        print("  python douyin_extractor.py --profile <sec_uid>")
        sys.exit(1)

    # 用户主页视频扫描
    if args[0] == "--profile":
        sec_uid = args[1]
        print(f"\n获取用户主页视频: sec_uid 前40位 = {sec_uid[:40]}...")
        vids = get_profile_video_ids(sec_uid)
        print(f"找到 {len(vids)} 个视频:")
        for vid in vids[:20]:
            print(f"  https://www.douyin.com/video/{vid}")
        if len(vids) > 20:
            print(f"  ... 还有 {len(vids) - 20} 个")
        sys.exit(0)

    urls = []
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

        vid = result["video_id"]
        out_file = OUTPUT_DIR / f"douyin_{vid or 'unknown'}.json"
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已保存: {out_file}")

        if result["success"]:
            print(f"  标题: {result['title'][:80]}")
            print(f"  作者: {result['author']}")
            if result.get("sec_uid"):
                print(f"  sec_uid: {result['sec_uid'][:40]}...")
            if result.get("stats"):
                s = result["stats"]
                print(f"  统计: 👍{s.get('digg_count','?')} 💬{s.get('comment_count','?')} 🔄{s.get('share_count','?')} ⭐{s.get('collect_count','?')}")
            if result.get("stats_display"):
                print(f"  展示统计: {result['stats_display']}")
            if result.get("chapter_content"):
                print(f"  章节: {result['chapter_content'][:200]}")
            if result.get("caption"):
                print(f"  字幕: {result['caption'][:200]}")
            print(f"  描述: {result['description'][:200]}")
        else:
            print(f"  失败: {result['error']}")


if __name__ == "__main__":
    main()
