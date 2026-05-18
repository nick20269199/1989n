"""
大V雷达 - 批量视频转录
从 vv_radar.db 读取视频，通过 Playwright 调抖音API获取CDN地址（绕过反爬），
用 curl_cffi 下载视频，ffmpeg 提取音频，faster-whisper 转录。

用法:
  py vv_transcribe.py                    # 转录所有未转录视频
  py vv_transcribe.py --account yanbao60 # 只转录指定账号
  py vv_transcribe.py --limit 10         # 只转录前10个
  py vv_transcribe.py --force            # 重新转录已有的
  py vv_transcribe.py --priority         # 按优先级顺序（行家5人→专项→其余）
"""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 路径
DATA_DIR = Path("D:/1989n/stock_data")
DB_PATH = DATA_DIR / "vv_radar.db"
STATE_FILE = DATA_DIR / "vv_browser_state" / "state.json"
TRANSCRIPTS_DIR = DATA_DIR / "vv_transcripts"
AUDIO_DIR = DATA_DIR / "vv_audio"

# 上海时区
TZ_SH = timezone(timedelta(hours=8))

# 账号优先级（行家→专项→其余）
PRIORITY_ORDER = [
    "yanbao60",      # 口罩哥 - 最高优先
    "Trader9",       # Trader韭
    "xiaositv",      # 小司频道
    "Cyclequeen",    # 周期女王
    "HuDaMao.New",   # 胡大毛
    "85164940078",   # 好运佛系
    "kaixin2091",    # 凯心
    "Zihui518",      # 子辉先生
    "6052m9121",     # 太阳李博良
    "guojame",       # 创业魔法师
]

# ffmpeg 路径
def _find_ffmpeg():
    candidates = [
        r"D:\tools\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Users\1989n\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe",
    ]
    for fp in candidates:
        if os.path.exists(fp):
            return fp
    try:
        result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None

FFMPEG = _find_ffmpeg()


def ensure_dirs():
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_untranscribed(account=None, limit=None, force=False, priority=False):
    """从数据库获取待转录视频列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if force:
        query = "SELECT aweme_id, vv_id, desc, duration FROM vv_videos WHERE 1=1"
    else:
        query = "SELECT aweme_id, vv_id, desc, duration FROM vv_videos WHERE (transcript_text IS NULL OR transcript_text = '')"

    params = []
    if account:
        query += " AND vv_id = ?"
        params.append(account)

    if priority:
        # 按优先级排序
        order_map = {v: i for i, v in enumerate(PRIORITY_ORDER)}
        c.execute(query, params)
        rows = c.fetchall()
        rows.sort(key=lambda r: order_map.get(r["vv_id"], 99))
        if limit:
            rows = rows[:limit]
    else:
        query += " ORDER BY vv_id, aweme_id"
        if limit:
            query += f" LIMIT {limit}"
        c.execute(query, params)
        rows = c.fetchall()

    conn.close()
    return rows


def save_transcript(aweme_id, transcript_text, transcript_path):
    """保存转录结果到数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE vv_videos
        SET transcript_text = ?, transcript_path = ?, push_status = 'transcribed'
        WHERE aweme_id = ?
    """, (transcript_text, transcript_path, aweme_id))
    conn.commit()
    conn.close()


def mark_failed(aweme_id, error_msg):
    """标记转录失败"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE vv_videos
        SET push_status = ?, transcript_text = ?
        WHERE aweme_id = ?
    """, (f"failed: {error_msg[:200]}", f"ERROR: {error_msg[:500]}", aweme_id))
    conn.commit()
    conn.close()


async def get_video_url_api(page, aweme_id):
    """通过抖音详情API获取视频CDN地址（不需要导航到视频页）"""
    try:
        result = await page.evaluate("""
            async (aid) => {
                const resp = await fetch('/aweme/v1/web/aweme/detail/?aweme_id=' + aid);
                const data = await resp.json();
                const detail = data.aweme_detail;
                if (!detail || !detail.video) return null;
                const addr = detail.video.play_addr;
                return (addr.url_list || []).slice(0, 3);
            }
        """, aweme_id)
        if result and len(result) > 0:
            return result[0]
        return None
    except Exception as e:
        print(f"  [WARN] 获取视频URL失败: {e}")
        return None


async def transcribe_batch(account=None, limit=None, force=False, priority=False):
    """批量转录主函数"""
    if not FFMPEG:
        print("[ERROR] ffmpeg 未找到")
        return

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[ERROR] faster-whisper 未安装: pip install faster-whisper")
        return

    if not STATE_FILE.exists():
        print("[ERROR] 登录态未初始化，先运行: py vv_login.py")
        return

    ensure_dirs()
    videos = get_untranscribed(account, limit, force, priority)

    if not videos:
        print("没有待转录的视频")
        return

    total = len(videos)
    total_duration_ms = sum(v["duration"] or 0 for v in videos)
    print(f"待转录: {total} 个视频, 总时长 ~{total_duration_ms // 60000} 分钟")
    print(f"估算时间: ~{total_duration_ms // 60000 * 2} 分钟 (Whisper small/CPU/int8)")
    print()

    # 加载 Whisper 模型
    print("加载 faster-whisper small 模型...")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    print("模型就绪\n")

    from playwright.async_api import async_playwright

    success = 0
    failed = 0
    skipped = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=str(STATE_FILE),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        # 先访问首页建立会话
        try:
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass  # 验证码页超时不阻塞流程，JS上下文仍可用
        await page.wait_for_timeout(2000)

        start_time = time.time()

        for i, v in enumerate(videos):
            aweme_id = v["aweme_id"]
            vv_id = v["vv_id"]
            desc = (v["desc"] or "")[:60]
            duration_s = (v["duration"] or 0) / 1000

            elapsed = time.time() - start_time
            eta = (elapsed / max(i, 1)) * (total - i) if i > 0 else 0
            print(f"[{i+1}/{total}] {vv_id} | {duration_s:.0f}s | {desc}")

            # 检查是否已转录（非force模式）
            if not force:
                transcript_file = TRANSCRIPTS_DIR / f"{aweme_id}.txt"
                if transcript_file.exists():
                    existing = transcript_file.read_text(encoding="utf-8")
                    if existing and not existing.startswith("ERROR:"):
                        print(f"  -> 跳过 (已有转录)")
                        save_transcript(aweme_id, existing, str(transcript_file))
                        skipped += 1
                        continue

            # Step 1: 获取视频URL
            video_url = await get_video_url_api(page, aweme_id)
            if not video_url:
                print(f"  -> 失败 (无视频URL)")
                mark_failed(aweme_id, "无法获取视频URL")
                failed += 1
                continue

            # Step 2: 用 curl_cffi 下载视频 (模拟浏览器指纹绕过CDN鉴权)
            audio_path = AUDIO_DIR / f"{aweme_id}.wav"
            if not audio_path.exists():
                print(f"  下载视频...")
                video_file = AUDIO_DIR / f"{aweme_id}.mp4"
                try:
                    from curl_cffi import requests as curl_requests
                    resp = curl_requests.get(
                        video_url,
                        headers={"Referer": "https://www.douyin.com/"},
                        impersonate="chrome131",
                        timeout=300
                    )

                    if resp.status_code == 403:
                        # URL过期，重新获取
                        print(f"  URL过期，重新获取...")
                        video_url = await get_video_url_api(page, aweme_id)
                        if not video_url:
                            print(f"  -> 重新获取URL也失败")
                            mark_failed(aweme_id, "无法获取视频URL")
                            failed += 1
                            continue
                        resp = curl_requests.get(
                            video_url,
                            headers={"Referer": "https://www.douyin.com/"},
                            impersonate="chrome131",
                            timeout=300
                        )

                    if resp.status_code != 200:
                        print(f"  -> 下载失败 (HTTP {resp.status_code})")
                        mark_failed(aweme_id, f"CDN下载失败 HTTP {resp.status_code}")
                        failed += 1
                        continue

                    video_bytes = resp.content
                    print(f"  下载完成: {len(video_bytes)/1024/1024:.1f}MB")
                    video_file.write_bytes(video_bytes)

                except Exception as e:
                    print(f"  -> 下载异常: {e}")
                    mark_failed(aweme_id, str(e))
                    failed += 1
                    continue

                # ffmpeg 提取音频
                print(f"  提取音频...")
                ok = subprocess.run([
                    FFMPEG, "-i", str(video_file),
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    str(audio_path), "-y",
                ], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")

                # 删除视频文件节省空间
                video_file.unlink(missing_ok=True)

                if ok.returncode != 0 or not audio_path.exists():
                    err = ok.stderr[-200:] if ok.stderr else "未知错误"
                    print(f"  -> 下载失败: {err}")
                    mark_failed(aweme_id, f"下载失败: {err}")
                    failed += 1
                    continue

            # Step 3: 转录
            print(f"  转录中...")
            transcript_file = TRANSCRIPTS_DIR / f"{aweme_id}.txt"
            try:
                segments, info = model.transcribe(
                    str(audio_path),
                    language="zh",
                    beam_size=5,
                    vad_filter=False,
                )

                lines = []
                for seg in segments:
                    ts = f"[{seg.start:6.1f}s - {seg.end:6.1f}s]"
                    lines.append(f"{ts} {seg.text.strip()}")

                transcript = "\n".join(lines)
                transcript_file.write_text(transcript, encoding="utf-8")

                # 清理音频文件节省空间
                audio_path.unlink(missing_ok=True)

                save_transcript(aweme_id, transcript, str(transcript_file))
                print(f"  -> 转录成功 ({len(lines)} 段, {len(transcript)} 字符, lang={info.language})")
                success += 1

            except Exception as e:
                print(f"  -> 转录失败: {e}")
                mark_failed(aweme_id, str(e))
                failed += 1

            # 进度统计
            if i > 0 and i % 10 == 0:
                elapsed = time.time() - start_time
                rate = elapsed / i
                eta_remaining = rate * (total - i)
                print(f"  --- 进度: {success}成功 {failed}失败 {skipped}跳过 | "
                      f"耗时 {elapsed/60:.1f}min | ETA {eta_remaining/60:.1f}min ---")

        await browser.close()

    print(f"\n===== 转录完成 =====")
    print(f"成功: {success}, 失败: {failed}, 跳过: {skipped}")
    print(f"总耗时: {(time.time() - start_time)/60:.1f} 分钟")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="大V雷达 - 批量视频转录")
    parser.add_argument("--account", help="只转录指定账号")
    parser.add_argument("--limit", type=int, help="限制转录数量")
    parser.add_argument("--force", action="store_true", help="重新转录已有")
    parser.add_argument("--priority", action="store_true", help="按优先级顺序")
    args = parser.parse_args()

    asyncio.run(transcribe_batch(
        account=args.account,
        limit=args.limit,
        force=args.force,
        priority=args.priority,
    ))


if __name__ == "__main__":
    main()
