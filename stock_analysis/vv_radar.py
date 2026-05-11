"""
大V雷达 - 抖音认知上升期大V内容监控
每小时抓取关注大V的新视频，四维分析（话题/选人逻辑/标的/空间）

用法:
  python vv_radar.py fetch          # 抓取所有关注大V的新视频
  python vv_radar.py add <抖音号>    # 添加关注
  python vv_radar.py remove <抖音号> # 取消关注
  python vv_radar.py list            # 列出关注列表
  python vv_radar.py report <抖音号> # 查看某大V最新报告
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 路径
DATA_DIR = Path("D:/1989n/stock_data")
DB_PATH = DATA_DIR / "stock.db"
COOKIES_PATH = DATA_DIR / "douyin_cookies.txt"
RADAR_DB_PATH = DATA_DIR / "vv_radar.db"
TRANSCRIPTS_DIR = DATA_DIR / "vv_transcripts"
SCREENSHOT_DIR = DATA_DIR / "screenshots"

# 上海时区
TZ_SH = timezone(timedelta(hours=8))


def ensure_dirs():
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def init_db():
    """初始化专用数据库"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    # 关注列表
    c.execute("""
        CREATE TABLE IF NOT EXISTS vv_follows (
            id TEXT PRIMARY KEY,           -- 抖音号
            name TEXT,                      -- 昵称
            sec_uid TEXT,                   -- 抖音内部UID
            added_at TEXT,                  -- 添加时间
            last_fetch_at TEXT,             -- 最后抓取时间
            total_videos INTEGER DEFAULT 0, -- 累计抓取视频数
            notes TEXT                      -- 备注
        )
    """)
    # 视频记录
    c.execute("""
        CREATE TABLE IF NOT EXISTS vv_videos (
            aweme_id TEXT PRIMARY KEY,      -- 抖音视频ID
            vv_id TEXT,                     -- 大V抖音号
            desc TEXT,                      -- 视频描述
            create_time INTEGER,            -- 发布时间(unix)
            fetched_at TEXT,                -- 抓取时间
            duration INTEGER,               -- 时长(秒)
            cover_url TEXT,                 -- 封面URL
            video_url TEXT,                 -- 视频URL
            transcript_path TEXT,           -- 转录文件路径
            transcript_text TEXT,           -- 转录文本(短)
            analysis_json TEXT,             -- 分析结果JSON
            push_status TEXT DEFAULT 'pending'  -- pending/pushed/skipped
        )
    """)
    # 分析结果
    c.execute("""
        CREATE TABLE IF NOT EXISTS vv_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aweme_id TEXT UNIQUE,
            vv_id TEXT,
            vv_name TEXT,
            topics TEXT,                    -- 涉及话题
            logic_why TEXT,                 -- 选人逻辑
            tickers TEXT,                   -- 提到的标的
            upside_analysis TEXT,           -- 空间分析
            confidence TEXT,                -- 置信度 high/medium/low
            raw_response TEXT,              -- Claude原始回复
            analyzed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def parse_netscape_cookies(path):
    """解析Netscape格式cookies为Playwright格式"""
    cookies = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                domain = parts[0]
                cookies.append({
                    'name': parts[5],
                    'value': parts[6],
                    'domain': domain,
                    'path': parts[2],
                    'expires': int(parts[4]) if parts[4] and parts[4] != '0' else -1,
                    'httpOnly': parts[1] == 'TRUE',
                    'secure': parts[3] == 'TRUE',
                })
    return cookies


async def fetch_user_videos(vv_id, sec_uid):
    """直接调用抖音API抓取用户帖子（需要sec_uid）"""
    from playwright.async_api import async_playwright

    STATE_FILE = DATA_DIR / "vv_browser_state" / "state.json"
    if not STATE_FILE.exists():
        return None, "登录态未初始化，请先运行 python vv_login.py 扫码登录"

    if not sec_uid:
        return None, "缺少sec_uid，请先在搜索结果中点进用户主页获取"

    videos = []
    error_msg = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            storage_state=str(STATE_FILE),
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        try:
            # 先访问首页建立会话
            await page.goto('https://www.douyin.com/', wait_until='load', timeout=60000)
            await page.wait_for_timeout(3000)

            # 直接调API获取帖子
            cursor = 0
            max_pages = 3  # 最多翻3页，抓60条
            for page_num in range(max_pages):
                result = await page.evaluate('''
                    async (params) => {
                        const query = new URLSearchParams({
                            device_platform: 'webapp',
                            aid: '6383',
                            channel: 'channel_pc_web',
                            sec_user_id: params.sec_uid,
                            max_cursor: String(params.cursor),
                            count: '20',
                            publish_video_strategy_type: '2',
                        });
                        const resp = await fetch('/aweme/v1/web/aweme/post/?' + query.toString());
                        return await resp.json();
                    }
                ''', {'sec_uid': sec_uid, 'cursor': cursor})

                aweme_list = result.get('aweme_list', [])
                if not aweme_list:
                    break

                for aweme in aweme_list:
                    stats = aweme.get('statistics', {})
                    video_info = aweme.get('video', {})
                    videos.append({
                        'aweme_id': aweme.get('aweme_id'),
                        'desc': aweme.get('desc', ''),
                        'create_time': aweme.get('create_time'),
                        'duration': video_info.get('duration', 0),
                        'cover_url': (video_info.get('cover', {}) or {}).get('url_list', [''])[0] if video_info.get('cover') else '',
                        'video_play_addr': (video_info.get('play_addr', {}) or {}).get('url_list', [''])[0] if video_info.get('play_addr') else '',
                        'play_count': stats.get('play_count', 0),
                        'digg_count': stats.get('digg_count', 0),
                        'comment_count': stats.get('comment_count', 0),
                        'share_count': stats.get('share_count', 0),
                    })

                cursor = result.get('max_cursor', 0)
                if not result.get('has_more'):
                    break

        except Exception as e:
            error_msg = str(e)

        await browser.close()

    return videos, error_msg


def save_videos_to_db(vv_id, videos):
    """保存新视频到数据库，返回新增数量"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    new_count = 0

    for v in videos:
        try:
            c.execute("""
                INSERT OR IGNORE INTO vv_videos
                (aweme_id, vv_id, desc, create_time, fetched_at, duration, cover_url, video_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                v['aweme_id'], vv_id, v['desc'], v['create_time'],
                datetime.now(TZ_SH).isoformat(), v['duration'],
                v.get('cover_url', ''), v.get('video_play_addr', '')
            ))
            if c.rowcount > 0:
                new_count += 1
        except Exception as e:
            print(f"  保存视频 {v['aweme_id']} 失败: {e}")

    conn.commit()

    # 更新关注列表
    if new_count > 0:
        c.execute("""
            UPDATE vv_follows SET
                last_fetch_at = ?,
                total_videos = total_videos + ?
            WHERE id = ?
        """, (datetime.now(TZ_SH).isoformat(), new_count, vv_id))

    conn.commit()
    conn.close()
    return new_count


def get_new_videos(vv_id, limit=5):
    """获取待分析的新视频"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT aweme_id, desc, create_time, duration
        FROM vv_videos
        WHERE vv_id = ? AND push_status = 'pending'
        ORDER BY create_time DESC
        LIMIT ?
    """, (vv_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_follows():
    """获取关注列表"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, added_at, last_fetch_at, total_videos FROM vv_follows ORDER BY added_at")
    rows = c.fetchall()
    conn.close()
    return rows


def add_follow(vv_id, name=''):
    """添加关注"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO vv_follows (id, name, added_at)
        VALUES (?, ?, ?)
    """, (vv_id, name or vv_id, datetime.now(TZ_SH).isoformat()))
    conn.commit()
    conn.close()


def remove_follow(vv_id):
    """取消关注"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM vv_follows WHERE id = ?", (vv_id,))
    conn.commit()
    conn.close()


def get_pending_for_analysis():
    """获取所有待分析的视频（跨所有大V）"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT v.aweme_id, v.vv_id, v.desc, v.create_time, v.duration,
               f.name as vv_name
        FROM vv_videos v
        LEFT JOIN vv_follows f ON v.vv_id = f.id
        WHERE v.push_status = 'pending'
        ORDER BY v.create_time DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_all():
    """抓取所有关注大V的新视频"""
    conn = sqlite3.connect(RADAR_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, sec_uid FROM vv_follows ORDER BY added_at")
    follows = c.fetchall()
    conn.close()

    if not follows:
        print("暂无关註大V。用 'python vv_radar.py add <抖音号>' 添加")
        return

    total_new = 0
    statuses = []

    for f in follows:
        vv_id = f[0]
        name = f[1] or vv_id
        sec_uid = f[2] or ''
        print(f"\n{'='*50}")
        print(f"抓取: {name} (@{vv_id})")
        print(f"{'='*50}")

        videos, error = asyncio.run(fetch_user_videos(vv_id, sec_uid))

        if error:
            print(f"  [错误] {error}")
            statuses.append({'vv_id': vv_id, 'status': 'error', 'msg': error})
            continue

        if not videos:
            print(f"  [空] 未获取到视频（可能是页面结构变更或账号无视频）")
            statuses.append({'vv_id': vv_id, 'status': 'empty', 'msg': '无视频'})
            continue

        new_count = save_videos_to_db(vv_id, videos)
        total_new += new_count
        print(f"  [OK] {len(videos)} 个视频，{new_count} 个新增")
        statuses.append({
            'vv_id': vv_id,
            'status': 'ok',
            'total': len(videos),
            'new': new_count
        })

    print(f"\n总计: {total_new} 个新视频")
    return statuses


def print_pending():
    """打印待分析视频"""
    items = get_pending_for_analysis()
    if not items:
        print("暂无待分析视频")
        return

    by_vv = {}
    for item in items:
        vid = item['vv_id']
        if vid not in by_vv:
            by_vv[vid] = []
        by_vv[vid].append(item)

    for vv_id, videos in by_vv.items():
        vv_name = videos[0].get('vv_name', vv_id)
        print(f"\n--- {vv_name} (@{vv_id}) ---")
        for v in videos:
            ts = datetime.fromtimestamp(v['create_time'], tz=TZ_SH).strftime('%m-%d %H:%M')
            desc = v['desc'][:80] if v['desc'] else '(无描述)'
            print(f"  [{ts}] {desc}")


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    ensure_dirs()
    init_db()

    if len(sys.argv) < 2:
        print("大V雷达 v1.0")
        print("  python vv_radar.py fetch         - 抓取所有关注大V的新视频")
        print("  python vv_radar.py add <抖音号>   - 添加关注")
        print("  python vv_radar.py remove <抖音号>- 取消关注")
        print("  python vv_radar.py list           - 关注列表")
        print("  python vv_radar.py pending        - 待分析视频")
        print("  python vv_radar.py status         - 状态概览")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'fetch':
        fetch_all()

    elif cmd == 'add':
        if len(sys.argv) < 3:
            print("用法: python vv_radar.py add <抖音号> [昵称]")
            sys.exit(1)
        vv_id = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ''
        add_follow(vv_id, name)
        print(f"已添加: {name or vv_id} (@{vv_id})")

    elif cmd == 'remove':
        if len(sys.argv) < 3:
            print("用法: python vv_radar.py remove <抖音号>")
            sys.exit(1)
        remove_follow(sys.argv[2])
        print(f"已移除: {sys.argv[2]}")

    elif cmd == 'list':
        follows = get_follows()
        if not follows:
            print("暂无关註")
        else:
            for f in follows:
                print(f"  @{f[0]:20s} {f[1] or '':10s} 添加:{f[2][:10]} 最后抓取:{f[3] or '从未'}  累计:{f[4]}视频")

    elif cmd == 'pending':
        print_pending()

    elif cmd == 'status':
        follows = get_follows()
        conn = sqlite3.connect(RADAR_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(CASE WHEN push_status='pending' THEN 1 ELSE 0 END) FROM vv_videos")
        total, pending = c.fetchone()
        conn.close()
        print(f"关注: {len(follows)} 个大V")
        print(f"累计视频: {total or 0}")
        print(f"待分析: {pending or 0}")
