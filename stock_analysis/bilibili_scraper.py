"""
B站视频列表获取工具 - 获取用户视频、搜索视频、过滤和保存

B站 API:
  - 用户视频列表: api.bilibili.com/x/space/wbi/arc/search
  - 视频搜索: api.bilibili.com/x/web-interface/wbi/search/type
  - 视频详情: api.bilibili.com/x/web-interface/view

WBI 签名:
  需要 img_key + sub_key (从 nav 接口获取)
  w_rid = md5(query_string + mixin_key)

Rate Limit: ~5 req/sec (B站限制，通过 sleep 控制)

Output:
  - bilibili_all_videos.json
  - bilibili_relevant_videos.json
  - bilibili_videos.json
  保存到 STOCK_DATA_DIR
"""

import hashlib
import json
import logging
import re
import sys
import time
import urllib.parse
from pathlib import Path

from config import STOCK_DATA_DIR, HEADERS

logger = logging.getLogger("bilibili_scraper")

# === 常量 ===
BILIBILI_API_BASE = "https://api.bilibili.com"
RATE_LIMIT_INTERVAL = 0.25  # 请求间隔 (秒)，~4 req/sec
DEFAULT_PAGE_SIZE = 50
SEARCH_PAGE_SIZE = 20

# requests 检测
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests 不可用，B站抓取器无法工作")

# === WBI 混肴密钥表 ===
_WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
]

# WBI keys 缓存
_WBI_KEYS_CACHE: tuple[str, str] | None = None
_WBI_KEYS_CACHE_TIME: float = 0
_WBI_KEYS_TTL: float = 3600  # 1 小时


def _rate_limit() -> None:
    """频率限制: 等待以确保不超过 ~4-5 req/sec。"""
    time.sleep(RATE_LIMIT_INTERVAL)


def _fetch_wbi_keys() -> tuple[str, str] | None:
    """
    获取 B站 WBI 签名密钥 (img_key, sub_key)。

    从 https://api.bilibili.com/x/web-interface/nav 获取 wbi_img，
    解析其中的 img_url 和 sub_url，提取文件名的 key 部分。
    """
    global _WBI_KEYS_CACHE, _WBI_KEYS_CACHE_TIME

    now = time.time()
    if _WBI_KEYS_CACHE and (now - _WBI_KEYS_CACHE_TIME) < _WBI_KEYS_TTL:
        return _WBI_KEYS_CACHE

    if not REQUESTS_AVAILABLE:
        return None

    try:
        resp = requests.get(
            f"{BILIBILI_API_BASE}/x/web-interface/nav",
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        wbi_img = data.get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        if img_url and sub_url:
            img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
            _WBI_KEYS_CACHE = (img_key, sub_key)
            _WBI_KEYS_CACHE_TIME = now
            logger.debug(f"WBI keys 已获取: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")
            return _WBI_KEYS_CACHE
    except Exception as e:
        logger.warning(f"获取 WBI keys 失败: {e}")

    return None


def _compute_mixin_key(raw_key: str) -> str:
    """计算 WBI 混肴密钥 (取前32字符，按映射表重排)。"""
    return "".join(
        raw_key[i] for i in _WBI_MIXIN_KEY_ENC_TAB if i < len(raw_key)
    )[:32]


def _wbi_sign(params: dict) -> dict:
    """为参数添加 WBI 签名 (w_rid, wts)。"""
    keys = _fetch_wbi_keys()
    if not keys:
        return params

    img_key, sub_key = keys
    mixin_key = _compute_mixin_key(img_key + sub_key)

    # 按 key 排序
    sorted_params = dict(sorted(params.items()))
    # 拼接查询串
    query_str = urllib.parse.urlencode(sorted_params)
    # md5(query_str + mixin_key)
    w_rid = hashlib.md5((query_str + mixin_key).encode()).hexdigest()

    sorted_params["w_rid"] = w_rid
    sorted_params["wts"] = str(int(time.time()))
    return sorted_params


def _api_get(endpoint: str, params: dict) -> dict:
    """
    调用 B站 API (带 WBI 签名和频率限制)。

    Args:
        endpoint: API 路径 (如 /x/space/wbi/arc/search)
        params: 查询参数

    Returns:
        dict: API 响应的 JSON
    """
    if not REQUESTS_AVAILABLE:
        logger.error("requests 不可用")
        return {"code": -1, "message": "requests not available"}

    _rate_limit()
    signed_params = _wbi_sign(params)

    try:
        resp = requests.get(
            f"{BILIBILI_API_BASE}{endpoint}",
            params=signed_params,
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error(f"B站 API 超时: {endpoint}")
        return {"code": -1, "message": "timeout"}
    except requests.exceptions.RequestException as e:
        logger.error(f"B站 API 请求失败: {endpoint} - {e}")
        return {"code": -1, "message": str(e)}


# ============================================================
# 公共 API
# ============================================================

def get_bilibili_videos(uid: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """
    获取指定用户的视频列表。

    Args:
        uid: B站用户 UID
        page: 页码 (从1开始)
        page_size: 每页数量 (最大50)

    Returns:
        list[dict]: 视频信息列表，每个 dict 包含:
            - bvid: BV号
            - title: 标题
            - description: 描述
            - play: 播放量
            - created: 发布时间戳
            - length: 视频长度 (mm:ss)
            - pic: 封面URL
            - comment: 评论数
            - typeid: 分区ID
    """
    logger.info(f"获取用户视频: uid={uid}, page={page}, page_size={page_size}")

    params = {
        "mid": uid,
        "pn": page,
        "ps": min(page_size, 50),
        "order": "pubdate",
    }

    result = _api_get("/x/space/wbi/arc/search", params)

    if result.get("code") != 0:
        logger.error(f"获取视频列表失败: {result.get('message', '未知错误')}")
        return []

    data = result.get("data", {})
    videos_raw = data.get("list", {}).get("vlist", [])

    videos: list[dict] = []
    for v in videos_raw:
        videos.append({
            "bvid": v.get("bvid", ""),
            "aid": v.get("aid", 0),
            "title": v.get("title", ""),
            "description": v.get("description", ""),
            "play": v.get("play", 0),
            "comment": v.get("comment", 0),
            "created": v.get("created", 0),
            "length": v.get("length", ""),
            "pic": v.get("pic", ""),
            "typeid": v.get("typeid", 0),
        })

    logger.info(f"获取到 {len(videos)} 个视频 (第{page}页)")
    return videos


def search_bilibili_videos(
    keyword: str,
    page: int = 1,
    page_size: int = SEARCH_PAGE_SIZE,
) -> list[dict]:
    """
    搜索 B站视频。

    Args:
        keyword: 搜索关键词
        page: 页码
        page_size: 每页数量 (最大50)

    Returns:
        list[dict]: 视频列表
    """
    logger.info(f"搜索视频: keyword={keyword}, page={page}")

    params = {
        "search_type": "video",
        "keyword": keyword,
        "page": page,
        "page_size": min(page_size, 50),
    }

    result = _api_get("/x/web-interface/wbi/search/type", params)

    if result.get("code") != 0:
        logger.error(f"搜索失败: {result.get('message', '未知错误')}")
        return []

    data = result.get("data", {})
    items = data.get("result", [])

    videos: list[dict] = []
    for item in items:
        videos.append({
            "bvid": item.get("bvid", ""),
            "aid": item.get("aid", 0),
            "title": _strip_html_tags(item.get("title", "")),
            "description": _strip_html_tags(item.get("description", "")),
            "author": item.get("author", ""),
            "mid": item.get("mid", 0),
            "play": item.get("play", 0),
            "danmaku": item.get("video_review", 0),
            "comment": item.get("comment", 0),
            "created": item.get("pubdate", 0),
            "length": item.get("duration", ""),
            "pic": item.get("pic", ""),
            "tag": item.get("tag", ""),
            "typeid": item.get("typeid", 0),
            "arcurl": item.get("arcurl", ""),
        })

    logger.info(f"搜索到 {len(videos)} 个视频")
    return videos


def get_video_info(bvid: str) -> dict | None:
    """
    获取视频详细信息。

    Args:
        bvid: 视频 BV 号

    Returns:
        dict | None: 视频详情
    """
    logger.info(f"获取视频详情: {bvid}")

    params = {"bvid": bvid}
    result = _api_get("/x/web-interface/view", params)

    if result.get("code") != 0:
        logger.error(f"获取视频详情失败: {result.get('message', '未知错误')}")
        return None

    data = result.get("data", {})
    owner = data.get("owner", {})
    stat = data.get("stat", {})

    return {
        "bvid": data.get("bvid", bvid),
        "aid": data.get("aid", 0),
        "title": data.get("title", ""),
        "description": data.get("desc", ""),
        "pic": data.get("pic", ""),
        "owner_name": owner.get("name", ""),
        "owner_mid": owner.get("mid", 0),
        "play": stat.get("view", 0),
        "danmaku": stat.get("danmaku", 0),
        "reply": stat.get("reply", 0),
        "favorite": stat.get("favorite", 0),
        "coin": stat.get("coin", 0),
        "share": stat.get("share", 0),
        "like": stat.get("like", 0),
        "created": data.get("pubdate", 0),
        "duration": data.get("duration", 0),
        "tname": (data.get("tname") or ""),
        "cid": data.get("cid", 0),
        "copyright": data.get("copyright", 0),
    }


def _strip_html_tags(text: str) -> str:
    """移除 HTML 标签 (B站搜索结果可能带 em 标签)。"""
    return re.sub(r"<[^>]+>", "", text)


def filter_relevant_videos(videos: list[dict], keywords: list[str]) -> list[dict]:
    """
    根据关键词过滤相关视频。

    匹配规则: 标题或描述中包含任意关键词 (不区分大小写)。

    Args:
        videos: 视频列表
        keywords: 过滤关键词列表

    Returns:
        list[dict]: 匹配的视频列表，附带匹配的关键词
    """
    logger.info(f"过滤视频: 共{len(videos)}个, 关键词: {keywords}")

    filtered: list[dict] = []
    for v in videos:
        title = v.get("title", "").lower()
        desc = v.get("description", "").lower()
        text = f"{title} {desc}"

        matched: list[str] = []
        for kw in keywords:
            if kw.lower() in text:
                matched.append(kw)

        if matched:
            item = dict(v)  # 不修改原始数据
            item["matched_keywords"] = matched
            filtered.append(item)

    # 按匹配关键词数量排序
    filtered.sort(key=lambda x: len(x.get("matched_keywords", [])), reverse=True)
    logger.info(f"过滤后: {len(filtered)} 个相关视频")
    return filtered


def save_video_list(videos: list[dict], filename: str) -> str:
    """
    保存视频列表到 JSON 文件。

    Args:
        videos: 视频列表
        filename: 文件名 (不含路径)

    Returns:
        str: 保存的完整路径
    """
    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = STOCK_DATA_DIR / filename
    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(videos),
        "videos": videos,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"视频列表已保存: {filepath} ({len(videos)} 条)")
    return str(filepath)


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    """命令行入口: 搜索或列出 B站视频，过滤后保存为 JSON。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print("  python bilibili_scraper.py search <关键词> [--page N] [--save]")
        print("  python bilibili_scraper.py user <UID> [--page N] [--save]")
        print("  python bilibili_scraper.py info <BV号>")
        print()
        print("保存: 添加 --save 参数将结果保存到 STOCK_DATA_DIR")
        print("  bilibili_all_videos.json  (用户全部视频)")
        print("  bilibili_relevant_videos.json (过滤后的相关视频)")
        print("  bilibili_videos.json (搜索结果)")
        sys.exit(1)

    command = sys.argv[1].lower()
    save = "--save" in sys.argv

    # 解析参数
    page = 1
    for i, arg in enumerate(sys.argv):
        if arg == "--page" and i + 1 < len(sys.argv):
            try:
                page = int(sys.argv[i + 1])
            except ValueError:
                pass
        if arg.startswith("--page="):
            try:
                page = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    if command == "search":
        keyword = sys.argv[2] if len(sys.argv) > 2 else ""
        if not keyword:
            print("请提供搜索关键词")
            sys.exit(1)
        videos = search_bilibili_videos(keyword, page=page)
        if save and videos:
            save_video_list(videos, "bilibili_videos.json")

    elif command == "user":
        uid = sys.argv[2] if len(sys.argv) > 2 else ""
        if not uid:
            print("请提供用户 UID")
            sys.exit(1)
        videos = get_bilibili_videos(uid, page=page, page_size=50)
        if save and videos:
            save_video_list(videos, "bilibili_all_videos.json")

    elif command == "info":
        bvid = sys.argv[2] if len(sys.argv) > 2 else ""
        if not bvid:
            print("请提供视频 BV 号")
            sys.exit(1)
        info = get_video_info(bvid)
        if info:
            print(json.dumps(info, ensure_ascii=False, indent=2))
            if save:
                save_video_list([info], f"bilibili_{bvid}.json")
        else:
            print("获取视频信息失败")
            sys.exit(1)

    else:
        print(f"未知命令: {command}")
        print("支持: search, user, info")
        sys.exit(1)

    # 打印结果摘要
    if command in ("search", "user"):
        videos = videos  # type: ignore[possibly-undefined]
        print(f"\n找到 {len(videos)} 个视频:\n")
        for v in videos[:20]:
            play = v.get("play", 0)
            play_str = f"{play/10000:.1f}万" if play >= 10000 else str(play)
            title = v.get("title", "")[:80]
            print(f"  [{play_str}播放] {title}")
        if len(videos) > 20:
            print(f"  ... 还有 {len(videos) - 20} 个视频")


if __name__ == "__main__":
    main()
