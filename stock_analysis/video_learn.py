"""
视频学习工具 - 下载视频 → 提取字幕/语音转文字 → 分析内容
支持 B站 (bilibili), YouTube, 抖音 (douyin)

依赖:
  yt-dlp (视频下载)
  faster-whisper (语音转录，可选)
  百炼 qwen-vl-max API (内容分析，可选)

Output: 转录文本保存到 STOCK_DATA_DIR/bilibili_transcripts/
"""

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from config import STOCK_DATA_DIR, HEADERS

logger = logging.getLogger("video_learn")

# === 路径常量 ===
TRANSCRIPTS_DIR = STOCK_DATA_DIR / "bilibili_transcripts"
AUDIO_DIR = STOCK_DATA_DIR / "bilibili_audio"
VIDEO_DIR = STOCK_DATA_DIR / "bilibili_videos"

# 确保目录存在
for _d in [TRANSCRIPTS_DIR, AUDIO_DIR, VIDEO_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# === FFmpeg 路径 ===
_FFMPEG_CANDIDATES = [
    r"D:\tools\ffmpeg\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
]
FFMPEG_PATH = None
for _fp in _FFMPEG_CANDIDATES:
    if os.path.exists(_fp):
        FFMPEG_PATH = _fp
        break
if not FFMPEG_PATH:
    try:
        result = subprocess.run(
            ["where", "ffmpeg"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            FFMPEG_PATH = lines[0].strip()
    except Exception:
        pass

# yt-dlp 检测
try:
    _result = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True, text=True, timeout=10,
    )
    YTDLP_AVAILABLE = _result.returncode == 0
except Exception:
    YTDLP_AVAILABLE = False

# faster-whisper 检测
try:
    from faster_whisper import WhisperModel  # noqa: F401
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# requests 检测
try:
    import requests  # noqa: F401
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ============================================================
# 辅助函数
# ============================================================

def _run_ffmpeg(args: list[str], timeout: int = 300) -> bool:
    """运行 ffmpeg 命令。"""
    if not FFMPEG_PATH:
        logger.error("ffmpeg 未找到，请安装 ffmpeg")
        return False
    cmd = [FFMPEG_PATH] + args
    logger.debug(f"ffmpeg 命令: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            logger.warning(f"ffmpeg 返回非零: {result.stderr[:300]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"ffmpeg 超时 ({timeout}s)")
        return False
    except FileNotFoundError:
        logger.error(f"ffmpeg 未找到: {FFMPEG_PATH}")
        return False


def _run_ytdlp(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess | None:
    """运行 yt-dlp 命令。"""
    if not YTDLP_AVAILABLE:
        logger.error("yt-dlp 不可用，请安装: pip install yt-dlp")
        return None
    cmd = [sys.executable, "-m", "yt_dlp"] + args
    logger.debug(f"yt-dlp 命令: {' '.join(cmd)}")
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp 超时 ({timeout}s)")
        return None
    except Exception as e:
        logger.error(f"yt-dlp 运行异常: {e}")
        return None


# ============================================================
# B站 WBI 签名 (简化实现)
# ============================================================

# WBI 签名用到的混肴密钥 (B站 API 固定值)
_WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
]


def _get_wbi_keys() -> tuple[str, str] | None:
    """获取 B站 WBI 签名所需的 img_key 和 sub_key (简化实现)。

    正式实现应从 https://api.bilibili.com/x/web-interface/nav 接口
    获取 wbi_img 并解析。此处使用简化方式。
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("requests 不可用，WBI 签名跳过")
        return None
    try:
        import requests as req
        resp = req.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=HEADERS, timeout=10,
        )
        data = resp.json().get("data", {})
        wbi_img = data.get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        if not img_url or not sub_url:
            logger.warning("无法获取 WBI keys，跳过签名")
            return None
        # 从 URL 中提取文件名 (不含扩展名)
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        return (img_key, sub_key)
    except Exception as e:
        logger.warning(f"获取 WBI keys 失败: {e}")
        return None


def _wbi_sign(params: dict[str, str]) -> dict[str, str]:
    """为 B站 API 参数添加 WBI 签名。"""
    keys = _get_wbi_keys()
    if not keys:
        return params  # 无法签名则返回原参数
    img_key, sub_key = keys
    mixin_key = img_key + sub_key
    # 按大小重排 mixin_key
    wbi_mixin_key = "".join(
        mixin_key[i] for i in _WBI_MIXIN_KEY_ENC_TAB if i < len(mixin_key)
    )[:32]

    # 按 key 排序参数
    sorted_params = dict(sorted(params.items()))
    # 拼接查询串
    query_str = urllib.parse.urlencode(sorted_params)
    # 计算 w_rid (md5)
    w_rid = hashlib.md5((query_str + wbi_mixin_key).encode()).hexdigest()
    sorted_params["w_rid"] = w_rid
    sorted_params["wts"] = str(int(time.time()))
    return sorted_params


# ============================================================
# 核心函数
# ============================================================

def download_video(url: str, output_dir: str = "") -> str:
    """
    下载视频，返回本地文件路径。

    Args:
        url: 视频链接 (B站 / YouTube / 抖音)
        output_dir: 输出目录，默认使用 VIDEO_DIR

    Returns:
        str: 下载后的视频文件路径，失败返回空字符串

    支持平台:
        - B站 (bilibili.com): 使用 cookies (douyin_cookies.txt) 优先
        - YouTube (youtube.com): 代理支持
        - 抖音 (douyin.com): 使用 cookies
    """
    out_dir = Path(output_dir) if output_dir else VIDEO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not YTDLP_AVAILABLE:
        logger.error("yt-dlp 不可用，无法下载视频")
        return ""

    logger.info(f"开始下载视频: {url}")

    # 判断平台
    url_lower = url.lower()
    is_bilibili = "bilibili.com" in url_lower or "b23.tv" in url_lower
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    is_douyin = "douyin.com" in url_lower or "tiktok.com" in url_lower

    args = [
        # 输出模板: 标题+id
        "-o", str(out_dir / "%(title)s_%(id)s.%(ext)s"),
        # 不下载 play list
        "--no-playlist",
        # 不创建缩略图等额外文件
        "--no-mtime",
        "--embed-metadata",
        # 用户代理
        "--user-agent", HEADERS.get("User-Agent", ""),
        # 格式偏好
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    ]

    # 平台特定配置
    cookie_file = out_dir / "douyin_cookies.txt"
    if cookie_file.exists():
        args.extend(["--cookies", str(cookie_file)])
        logger.info(f"使用 cookies 文件: {cookie_file}")

    if is_youtube:
        # YouTube 可能需要代理
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        if proxy:
            args.extend(["--proxy", proxy])
            logger.info(f"使用代理: {proxy}")

    if is_douyin:
        args.extend(["--extractor-retries", "5"])

    args.append(url)

    result = _run_ytdlp(args, timeout=900)
    if result is None or result.returncode != 0:
        error_msg = result.stderr.strip() if result else "未知错误"
        logger.error(f"下载失败: {error_msg[:500]}")
        return ""

    # 从输出中找到下载的文件路径
    output_lines = result.stdout.split("\n")
    for line in reversed(output_lines):
        # yt-dlp 输出的典型行: "[download] Destination: /path/to/file.mp4"
        if "Destination:" in line:
            filepath = line.split("Destination:", 1)[1].strip()
            if os.path.exists(filepath):
                logger.info(f"下载完成: {filepath}")
                return filepath

    # 如果解析失败，尝试在目录中找最新文件
    try:
        files = sorted(out_dir.glob("*.mp4") + out_dir.glob("*.mkv") + out_dir.glob("*.flv"),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            logger.info(f"推断下载文件: {files[0]}")
            return str(files[0])
    except Exception:
        pass

    logger.warning("无法定位下载的文件")
    return ""


def extract_subtitles(video_path: str) -> str:
    """
    从视频中提取内嵌字幕。

    Args:
        video_path: 视频文件路径

    Returns:
        str: 字幕文本，失败返回空字符串
    """
    video = Path(video_path)
    if not video.exists():
        logger.error(f"视频文件不存在: {video_path}")
        return ""

    logger.info(f"提取字幕: {video_path}")
    subtitle_path = video.with_suffix(".srt")
    output_path = video.with_suffix(".txt")

    # 使用 ffmpeg 提取字幕流
    # 先探测字幕流
    probe_cmd = [
        FFMPEG_PATH, "-i", str(video),
        "-c", "copy", "-map", "0:s:0",
        str(subtitle_path), "-y",
        "-hide_banner", "-loglevel", "error",
    ]
    try:
        result = subprocess.run(
            probe_cmd, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and subtitle_path.exists():
            # 提取成功，将 srt 转为纯文本
            text = _srt_to_text(subtitle_path)
            output_path.write_text(text, encoding="utf-8")
            logger.info(f"字幕提取成功: {output_path} ({len(text)} 字符)")
            return text
    except Exception as e:
        logger.debug(f"内嵌字幕提取失败: {e}")

    logger.info("无内嵌字幕，将使用语音转录")
    return ""


def _srt_to_text(srt_path: Path) -> str:
    """将 SRT 字幕文件转为纯文本。"""
    try:
        content = srt_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = srt_path.read_text(encoding="gbk", errors="replace")

    # 移除 SRT 编号和时间戳
    lines = content.split("\n")
    text_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过数字行 (字幕序号)
        if re.match(r"^\d+$", line):
            continue
        # 跳过时间戳行
        if re.match(r"^\d{2}:\d{2}:\d{2}[,.]", line):
            continue
        # 跳过 SRT 标签
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)
    return "\n".join(text_lines)


def transcribe_video(video_path: str) -> str:
    """
    使用 faster-whisper 将视频音频转录为文字。

    Args:
        video_path: 视频文件路径

    Returns:
        str: 转录文本，失败返回空字符串
    """
    video = Path(video_path)
    if not video.exists():
        logger.error(f"视频文件不存在: {video_path}")
        return ""

    output_path = TRANSCRIPTS_DIR / f"{video.stem}.txt"
    if output_path.exists():
        logger.info(f"转录文本已存在: {output_path}")
        return output_path.read_text(encoding="utf-8")

    if not WHISPER_AVAILABLE:
        logger.error("faster-whisper 不可用，请安装: pip install faster-whisper")
        return ""

    if not FFMPEG_PATH:
        logger.error("ffmpeg 不可用，无法提取音频")
        return ""

    # 第一步: 提取音频为 WAV
    audio_path = AUDIO_DIR / f"{video.stem}.wav"
    logger.info(f"提取音频: {audio_path}")
    ok = _run_ffmpeg([
        "-i", str(video),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path), "-y",
    ], timeout=300)
    if not ok or not audio_path.exists():
        logger.error("音频提取失败")
        return ""

    # 第二步: 使用 faster-whisper 转录
    logger.info(f"语音转录中: {audio_path}")
    try:
        from faster_whisper import WhisperModel  # noqa: F811
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            str(audio_path),
            language="zh",
            beam_size=5,
            vad_filter=True,
        )
        logger.info(
            f"检测语言: {info.language} "
            f"(概率: {info.language_probability:.2f})"
        )

        lines: list[str] = []
        for seg in segments:
            ts = f"[{seg.start:6.1f}s - {seg.end:6.1f}s]"
            lines.append(f"{ts} {seg.text.strip()}")

        transcript = "\n".join(lines)
        output_path.write_text(transcript, encoding="utf-8")
        logger.info(
            f"转录完成: {output_path} "
            f"({len(lines)} 段, {len(transcript)} 字符)"
        )
        return transcript

    except Exception as e:
        logger.error(f"转录失败: {e}")
        return ""


def analyze_content(text: str, url: str = "") -> str:
    """
    分析转录内容并返回摘要。

    使用百炼 qwen-vl-max API 进行内容分析。
    如果 API 不可用，返回基于规则的基本统计。

    Args:
        text: 转录文本
        url: 视频原始链接 (可选，用于上下文)

    Returns:
        str: 分析摘要 (Markdown 格式)
    """
    if not text.strip():
        logger.warning("无文本内容可分析")
        return "*无文本内容*"

    logger.info(f"分析内容: {len(text)} 字符")

    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if api_key and REQUESTS_AVAILABLE:
        return _analyze_with_llm(text, url, api_key)
    else:
        return _analyze_basic(text, url)


def _analyze_with_llm(text: str, url: str, api_key: str) -> str:
    """使用百炼 API 分析内容。"""
    try:
        import requests as req
    except ImportError:
        return _analyze_basic(text, url)

    # 限制文本长度
    max_chars = 8000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(内容已截断)"

    prompt = (
        "请分析以下视频转录内容，用中文总结:\n\n"
        "1. **核心主题**: 视频主要讲了什么 (1-2句)\n"
        "2. **关键观点**: 3-5个最重要的观点或信息点\n"
        "3. **金句摘录**: 2-3句值得记录的原话\n"
        "4. **可操作洞察**: 是否有值得跟进的信息或行动建议\n\n"
        f"原始链接: {url}\n\n"
        f"{text}"
    )

    payload = {
        "model": "qwen-turbo",
        "messages": [
            {"role": "system", "content": "你是一个专业的视频内容分析师，擅长提炼关键信息。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    try:
        resp = req.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"LLM 分析失败，回退到基础分析: {e}")
        return _analyze_basic(text, url)


def _analyze_basic(text: str, url: str = "") -> str:
    """基于规则的基础分析。"""
    lines = text.strip().split("\n")
    total_chars = len(text)
    total_lines = len(lines)

    # 统计各段时长
    durations: list[float] = []
    for line in lines:
        m = re.match(r"\[[\d.]+s - ([\d.]+)s\]", line)
        if m:
            durations.append(float(m.group(1)))

    total_duration = durations[-1] if durations else 0

    # 关键词统计
    keywords = [
        "AI", "人工智能", "大模型", "GPU", "算力", "芯片",
        "股票", "投资", "市场", "量化", "策略",
        "机器人", "自动驾驶", "半导体",
        "风险", "收益", "估值", "财报",
        "买入", "卖出", "持仓", "止损",
    ]
    kw_counts: dict[str, int] = {}
    for kw in keywords:
        count = text.count(kw)
        if count > 0:
            kw_counts[kw] = count

    parts = [
        f"## 视频内容基础分析\n",
        f"- **总字符数**: {total_chars}",
        f"- **总行数**: {total_lines}",
        f"- **预估时长**: {total_duration:.0f}秒 ({total_duration/60:.1f}分钟)",
    ]
    if url:
        parts.append(f"- **来源**: {url}")
    parts.append("")

    if kw_counts:
        parts.append("### 关键词频率")
        sorted_kw = sorted(kw_counts.items(), key=lambda x: x[1], reverse=True)
        for kw, count in sorted_kw[:10]:
            bar = "#" * min(count, 20)
            parts.append(f"- **{kw}**: {count}次 {bar}")
        parts.append("")

    # 提取前几行作为摘要
    parts.append("### 内容预览 (前5行)")
    for line in lines[:5]:
        parts.append(f"> {line[:120]}")

    return "\n".join(parts)


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    """命令行入口: 传入 URL，下载视频并提取字幕/转录，最后分析。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("用法: python video_learn.py <视频URL>")
        print("支持: B站 (bilibili), YouTube, 抖音 (douyin)")
        print()
        print("环境变量:")
        print("  ANTHROPIC_AUTH_TOKEN - 百炼 API 密钥 (用于内容分析)")
        print("  HTTP_PROXY / HTTPS_PROXY - 代理 (用于 YouTube)")
        sys.exit(1)

    url = sys.argv[1]
    logger.info(f"=== 视频学习工具 ===\n    链接: {url}")

    # Step 1: 下载视频
    video_path = download_video(url)
    if not video_path:
        logger.error("视频下载失败，退出")
        sys.exit(1)

    # Step 2: 尝试提取内嵌字幕
    text = extract_subtitles(video_path)

    # Step 3: 若无字幕则语音转录
    if not text:
        text = transcribe_video(video_path)

    if not text:
        logger.error("无法获取视频文本内容 (既无字幕也转录失败)")
        sys.exit(1)

    # Step 4: 分析内容
    summary = analyze_content(text, url)

    print()
    print("=" * 60)
    print(summary)
    print("=" * 60)

    logger.info("视频学习完成")


if __name__ == "__main__":
    main()
