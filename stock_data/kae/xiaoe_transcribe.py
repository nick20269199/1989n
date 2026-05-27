"""
小鹅通 — 视频下载 + 语音转录 + 内容分析 完整管线

流程:
1. 从 xiaoe_video_urls.json 读取课程+视频URL
2. 用 ffmpeg 提取音频 (m3u8 → wav)
3. 用 faster-whisper 转录 (支持多进程并行)
4. 用 Qwen (DashScope) 分析内容

用法:
  # 处理单个课程 (by index)
  python xiaoe_transcribe.py --index 0
  # 并行处理所有课程 (默认4进程)
  python xiaoe_transcribe.py --all --parallel 4
  # 只提取音频，不转录
  python xiaoe_transcribe.py --index 0 --audio-only
  # 列出课程
  python xiaoe_transcribe.py --list
"""
import argparse
import json
import logging
import multiprocessing as mp
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CAPTURE_DIR = Path("D:/1989n/stock_data/kae")
AUDIO_DIR = CAPTURE_DIR / "audio"
TRANSCRIPT_DIR = CAPTURE_DIR / "transcripts"
ANALYSIS_DIR = CAPTURE_DIR / "analysis"
VIDEO_URLS_FILE = CAPTURE_DIR / "xiaoe_video_urls.json"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("xiaoe_transcribe")


def log_msg(msg):
    log.info(msg)


def get_courses():
    """Load course list from video URLs JSON."""
    if not VIDEO_URLS_FILE.exists():
        log.error(f"Video URLs file not found: {VIDEO_URLS_FILE}")
        log.error("Run xiaoe_auto_capture.py first to get fresh URLs")
        sys.exit(1)

    with open(VIDEO_URLS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    courses = []
    for rid, info in data.get("results", {}).items():
        entries = info.get("video_entries", [])
        if not entries:
            continue
        # Use first entry's URL (线路1, 原画)
        courses.append({
            "rid": rid,
            "title": info.get("title", rid),
            "m3u8_url": entries[0]["url"],
            "line": entries[0].get("line", ""),
            "resolution": entries[0].get("resolution", ""),
        })
    return courses


def extract_audio(m3u8_url: str, output_path: Path) -> bool:
    """Download m3u8 stream and extract audio as WAV using ffmpeg."""
    log_msg(f"  Extracting audio: {output_path.name}")

    if output_path.exists() and output_path.stat().st_size > 100000:
        log_msg(f"  Audio already exists, skipping ({output_path.stat().st_size} bytes)")
        return True

    t0 = time.time()
    result = subprocess.run(
        ["ffmpeg", "-i", m3u8_url,
         "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1",
         "-y", str(output_path),
         "-hide_banner", "-loglevel", "error"],
        capture_output=True, text=True, timeout=7200,
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        log_msg(f"  ffmpeg failed ({result.returncode}): {result.stderr[:200]}")
        return False

    size = output_path.stat().st_size
    log_msg(f"  Audio extracted: {size//1024//1024}MB in {elapsed:.0f}s")
    return size > 10000


def transcribe_audio(audio_path: Path, output_path: Path, model_name: str = "medium") -> str:
    """Transcribe audio with faster-whisper, return text."""
    if output_path.exists() and output_path.stat().st_size > 100:
        text = output_path.read_text(encoding="utf-8")
        log_msg(f"  Transcript already exists ({len(text)} chars)")
        return text

    log_msg(f"  Loading whisper model ({model_name})...")
    t0 = time.time()

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            str(audio_path),
            language="zh",
            beam_size=5,
            vad_filter=True,
        )
        log_msg(f"  Language: {info.language} (p={info.language_probability:.2f})")

        lines = []
        seg_count = 0
        for seg in segments:
            seg_count += 1
            lines.append(f"[{seg.start:.1f}s-{seg.end:.1f}s] {seg.text.strip()}")

        text = "\n".join(lines)
        output_path.write_text(text, encoding="utf-8")
        elapsed = time.time() - t0

        # Get duration from audio file
        audio_dur = 0
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(audio_path)],
                capture_output=True, text=True, timeout=10,
            )
            audio_dur = float(r.stdout.strip() or 0)
        except:
            pass

        log_msg(f"  Transcribed {seg_count} segments, {len(text)} chars in {elapsed:.0f}s"
                f" ({audio_dur/elapsed:.1f}x realtime)")
        return text

    except ImportError:
        log.error("faster-whisper not installed. Run: pip install faster-whisper")
        return ""
    except Exception as e:
        log.error(f"  Transcription failed: {e}")
        return ""


def analyze_with_qwen(text: str, title: str) -> str:
    """Use Qwen (DashScope) to analyze transcript content."""
    if not text.strip():
        return "*无文本内容*"

    from dotenv import load_dotenv
    load_dotenv(Path("D:/1989n/stock_analysis/.env"))
    import os, requests

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return "*Qwen API 未配置*"

    # Truncate to avoid token limits
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(内容截断)"

    prompt = f"""请分析以下课程转录内容。

课程标题: {title}

要求:
1. **核心主题**: 这堂课主要讲了什么 (2-3句概括)
2. **关键观点**: 列出5-8个最重要的观点或知识点，每点配1-2句解释
3. **交易洞察**: 是否有具体的交易策略、方法、规则可以直接落地？列出具体可操作内容
4. **金句**: 2-3句值得记住的原话

转录内容:
{text}"""

    try:
        import requests as req
        resp = req.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-plus",
                "messages": [
                    {"role": "system", "content": "你是一个专业的交易课程分析师，擅长从讲课内容中提炼可操作的交易知识和策略。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log_msg(f"  Qwen analysis failed: {e}")
        return f"*分析失败: {e}*"


def process_course(course: dict, model_name: str = "small",
                   audio_only: bool = False, skip_audio: bool = False):
    """Process a single course: extract audio → transcribe → analyze."""
    rid = course["rid"]
    title = course["title"]
    m3u8_url = course["m3u8_url"]

    safe_name = _safe_name(course)
    audio_path = AUDIO_DIR / f"{safe_name}.wav"
    transcript_path = TRANSCRIPT_DIR / f"{safe_name}.txt"
    analysis_path = ANALYSIS_DIR / f"{safe_name}.md"

    log_msg(f"\n{'='*60}")
    log_msg(f"Course: {title}")
    log_msg(f"RID: {rid}")
    log_msg(f"Audio: {audio_path.name}")
    log_msg(f"{'='*60}")

    # Step 1: Extract audio
    if not skip_audio:
        if not extract_audio(m3u8_url, audio_path):
            log_msg("  Audio extraction failed, skipping")
            return False
    else:
        if not audio_path.exists():
            log_msg(f"  Audio not found at {audio_path}, can't skip")
            return False

    if audio_only:
        log_msg("  Audio-only mode, done.")
        return True

    # Step 2: Transcribe
    text = transcribe_audio(audio_path, transcript_path, model_name)
    if not text:
        log_msg("  Transcription failed")
        return False

    # Step 3: Analyze with Qwen
    log_msg(f"  Analyzing with Qwen...")
    analysis = analyze_with_qwen(text, title)
    if analysis and not analysis.startswith("*"):
        analysis_path.write_text(analysis, encoding="utf-8")
        log_msg(f"  Analysis saved to {analysis_path.name}")
    else:
        log_msg(f"  Analysis: {analysis}")

    return True


def _worker_init():
    """Initialize logging in worker processes."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _worker_process(course: dict, model_name: str = "small",
                    audio_only: bool = False, skip_audio: bool = False) -> dict:
    """Wrapper for process_course to be used with multiprocessing.
    Returns dict with course info and result."""
    _worker_init()
    pid = os.getpid()
    # Re-point module-level paths (they're Path objects which are serializable)
    global CAPTURE_DIR, AUDIO_DIR, TRANSCRIPT_DIR, ANALYSIS_DIR, VIDEO_URLS_FILE
    # These should already be correct since the module is imported

    try:
        ok = process_course(course, model_name=model_name,
                            audio_only=audio_only, skip_audio=skip_audio)
        return {
            "rid": course["rid"],
            "title": course["title"],
            "success": ok,
            "pid": pid,
        }
    except Exception as e:
        logging.getLogger("worker").error(f"Worker {pid} failed: {e}")
        return {
            "rid": course["rid"],
            "title": course["title"],
            "success": False,
            "error": str(e)[:200],
            "pid": pid,
        }


def main():
    parser = argparse.ArgumentParser(description="小鹅通视频转录分析")
    parser.add_argument("--index", type=int, default=None,
                        help="Process single course by index (0-based)")
    parser.add_argument("--all", action="store_true",
                        help="Process all courses")
    parser.add_argument("--model", default="small",
                        choices=["tiny", "base", "small", "medium"],
                        help="Whisper model size (default: small)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Parallel workers (default: 1, 0=auto CPU count)")
    parser.add_argument("--audio-only", action="store_true",
                        help="Only extract audio, skip transcription")
    parser.add_argument("--skip-audio", action="store_true",
                        help="Skip audio extraction, use existing audio")
    parser.add_argument("--list", action="store_true",
                        help="List available courses and exit")
    parser.add_argument("--refresh-urls", action="store_true",
                        help="Re-run capture to get fresh m3u8 URLs")

    args = parser.parse_args()

    # Refresh URLs if requested
    if args.refresh_urls:
        log_msg("Re-running video URL capture...")
        from xiaoe_auto_capture import main as capture_main
        capture_main()
        log_msg("URL capture complete.")

    courses = get_courses()
    if not courses:
        log_msg("No courses found!")
        sys.exit(1)

    if args.list:
        log_msg(f"\nAvailable courses ({len(courses)}):")
        for i, c in enumerate(courses):
            log_msg(f"  [{i}] {c['title'][:50]} | {c['rid'][:30]}")
        log_msg(f"\nUsage: python xiaoe_transcribe.py --index <N>")
        return

    if args.index is not None:
        if args.index < 0 or args.index >= len(courses):
            log_msg(f"Index {args.index} out of range (0-{len(courses)-1})")
            sys.exit(1)
        targets = [courses[args.index]]
    elif args.all:
        targets = courses
    else:
        log_msg("Specify --index N, --all, or --list")
        sys.exit(1)

    # Determine parallel count
    parallel = args.parallel
    if parallel == 0:
        parallel = mp.cpu_count()
    if parallel > len(targets):
        parallel = len(targets)

    t_start = time.time()
    log_msg(f"Processing {len(targets)} course(s) with {parallel} worker(s)...")

    if parallel <= 1:
        # Serial processing
        success = 0
        for i, c in enumerate(targets):
            ok = process_course(c, model_name=args.model,
                                audio_only=args.audio_only,
                                skip_audio=args.skip_audio)
            if ok:
                success += 1
            time.sleep(2)
    else:
        # Parallel processing
        # First: extract audio for ALL courses (fast, parallel-safe with ffmpeg)
        if not args.skip_audio and not args.audio_only:
            log_msg("Phase 1: Extracting audio for all courses...")
            audio_tasks = [(c, args.model, False, False) for c in targets]
            # Actually just extract audio first
            with mp.get_context("spawn").Pool(parallel, initializer=_worker_init) as pool:
                results = pool.starmap(_extract_audio_worker,
                                       [(c,) for c in targets])
                for r in results:
                    if r.get("success"):
                        log_msg(f"  Audio OK: {r['title'][:40]}")
                    else:
                        log_msg(f"  Audio FAIL: {r['title'][:40]} - {r.get('error','')}")

        # Phase 2: Transcribe in parallel
        if not args.audio_only:
            log_msg(f"\nPhase 2: Transcribing {len(targets)} course(s) with {parallel} workers...")
            executor = mp.get_context("spawn").Pool(parallel, initializer=_worker_init)
            results = executor.starmap(_worker_process,
                                       [(c, args.model, False, True)
                                        for c in targets])
            executor.close()
            executor.join()

            log_msg(f"\n{'='*60}")
            log_msg("Transcription Results:")
            success = 0
            for r in results:
                status = "OK" if r.get("success") else "FAIL"
                if status == "OK":
                    success += 1
                err = f" - {r.get('error','')}" if r.get("error") else ""
                log_msg(f"  [{status}] {r['title'][:45]} (PID:{r.get('pid','')}){err}")

            elapsed = time.time() - t_start
            log_msg(f"\nTranscription time: {elapsed/60:.0f}m {elapsed%60:.0f}s")
            log_msg(f"Average: {elapsed/len(targets)/60:.0f}m per course with {parallel} workers")

            # Phase 3: Analyze with Qwen (after all transcriptions done)
            log_msg(f"\nPhase 3: Analyzing transcripts with Qwen...")
            for i, c in enumerate(targets):
                safe_name = _safe_name(c)
                transcript_path = TRANSCRIPT_DIR / f"{safe_name}.txt"
                analysis_path = ANALYSIS_DIR / f"{safe_name}.md"
                if transcript_path.exists():
                    text = transcript_path.read_text(encoding="utf-8")
                    log_msg(f"  [{i+1}/{len(targets)}] Analyzing {c['title'][:40]}...")
                    analysis = analyze_with_qwen(text, c["title"])
                    if analysis and not analysis.startswith("*"):
                        analysis_path.write_text(analysis, encoding="utf-8")
                        log_msg(f"    Done -> {analysis_path.name}")
                    else:
                        log_msg(f"    Skipped: {analysis}")

            elapsed = time.time() - t_start
            log_msg(f"\n{'='*60}")
            log_msg(f"Total time: {elapsed/60:.0f}m {elapsed%60:.0f}s")
            log_msg(f"Done. {success}/{len(targets)} courses.")


def _safe_name(course: dict) -> str:
    name = f"{course['rid'][:15]}_{course['title'][:20]}"
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)


def _extract_audio_worker(course: dict) -> dict:
    """Extract audio only, for parallel audio extraction phase."""
    _worker_init()
    safe_name = _safe_name(course)
    audio_path = AUDIO_DIR / f"{safe_name}.wav"
    ok = extract_audio(course["m3u8_url"], audio_path)
    return {"title": course["title"], "success": ok, "rid": course["rid"]}


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    mp.freeze_support()
    main()
