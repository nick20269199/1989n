#!/usr/bin/env python3
"""
Video Transcriber: Extract audio from video and transcribe to text.

Usage:
    python transcribe.py <video_path_or_url>
    python transcribe.py <video_path_or_url> --local
    python transcribe.py <video_path_or_url> --output out.md
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AUDIO_FORMAT = "m4a"
AUDIO_BITRATE = "64k"

# China-accessible HuggingFace mirror for whisper model downloads
HF_MIRROR = "https://hf-mirror.com"


# ── ffmpeg discovery ──────────────────────────────────────────────────

def find_ffmpeg() -> str:
    for candidate in ["ffmpeg", "ffmpeg.exe"]:
        try:
            subprocess.run([candidate, "-version"], capture_output=True, check=True)
            return candidate
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    candidates = [
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\Gyan\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    for root in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        try:
            for match in Path(root).rglob("ffmpeg.exe"):
                return str(match)
        except (PermissionError, OSError):
            continue
    sys.exit("ERROR: ffmpeg not found. Install: winget install Gyan.FFmpeg")


def run(cmd: list[str], desc: str = "") -> subprocess.CompletedProcess:
    print(f"[{desc}]", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[:800]}", file=sys.stderr)
        sys.exit(f"Command failed: {desc}")
    return result


# ── Download strategies ───────────────────────────────────────────────

def download_via_ytdlp(url: str, outdir: str) -> str:
    """Standard yt-dlp for YouTube, B站, and most sites."""
    import yt_dlp
    ydl_opts = {
        "outtmpl": f"{outdir}/%(title)s.%(ext)s",
        "format": "best[height<=1080]/best",
        "quiet": True,
        "no_warnings": True,
    }
    # B站, YouTube work fine without cookies
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        print(f"Downloaded: {filename}", file=sys.stderr)
        return filename
    except Exception:
        return ""  # fall through to playwright


def download_via_playwright(url: str, outdir: str) -> str:
    """Browser-based download for Douyin/TikTok (bypasses cookie restrictions)."""
    import asyncio
    import requests as req

    async def _extract():
        from playwright.async_api import async_playwright
        video_url = None
        captured = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            async def on_response(response):
                ct = response.headers.get("content-type", "")
                cl = response.headers.get("content-length", "0")
                if "video/mp4" in ct:
                    u = response.url
                    # Real video hosts, exclude static/effect CDN
                    if any(d in u for d in ["douyinvod", "ixigua", "bytecdn"]):
                        captured.append((u, int(cl or 0)))
                    elif "douyin" in u and "douyinstatic" not in u and "effect" not in u:
                        captured.append((u, int(cl or 0)))

            page.on("response", on_response)

            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(8000)
            except Exception:
                pass  # timeout is fine, we got the responses

            await browser.close()

        # Pick the real video: largest file, not an effect/sticker
        captured.sort(key=lambda x: x[1], reverse=True)
        for u, size in captured:
            if "effect" not in u and "douyinstatic" not in u and "effectcdn" not in u:
                video_url = u
                break
        if not video_url and captured:
            video_url = captured[0][0]

        return video_url

    video_url = asyncio.run(_extract())
    if not video_url:
        sys.exit("Failed to find video URL on this page")

    print(f"Video URL: {video_url[:120]}...", file=sys.stderr)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": url,
    }
    resp = req.get(video_url, headers=headers, timeout=60)
    ext = "mp4"
    outpath = Path(outdir) / f"video.{ext}"
    outpath.write_bytes(resp.content)
    print(f"Downloaded: {outpath} ({len(resp.content)} bytes)", file=sys.stderr)
    return str(outpath)


def download(url: str, outdir: str) -> str:
    """Smart download: try yt-dlp first, fall back to Playwright for anti-bot sites."""
    print(f"Downloading: {url}", file=sys.stderr)

    result = download_via_ytdlp(url, outdir)
    if result and Path(result).stat().st_size > 100_000:
        return result

    print("yt-dlp failed or got small file, trying Playwright...", file=sys.stderr)
    return download_via_playwright(url, outdir)


# ── Audio Extraction ─────────────────────────────────────────────────

def extract_audio(video_path: str, audio_path: str, ffmpeg: str) -> None:
    run([
        ffmpeg, "-y", "-i", video_path,
        "-vn", "-acodec", "aac", "-b:a", AUDIO_BITRATE,
        "-ac", "1", "-ar", "16000",
        audio_path,
    ], "Extract audio")


# ── Transcription ────────────────────────────────────────────────────

def transcribe_openai(audio_path: str, language: str = "zh") -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("ERROR: OPENAI_API_KEY not set. Set it or use --local mode.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    file_size = Path(audio_path).stat().st_size
    if file_size > 25 * 1024 * 1024:
        return _transcribe_openai_chunked(audio_path, client, language)

    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=f,
            response_format="verbose_json", language=language,
            timestamp_granularities=["segment"],
        )
    return _format_openai_result(transcription)


def _transcribe_openai_chunked(audio_path: str, client, language: str) -> dict:
    from pydub import AudioSegment
    audio = AudioSegment.from_file(audio_path)
    chunk_ms = 10 * 60 * 1000
    chunks = [audio[i:i + chunk_ms] for i in range(0, len(audio), chunk_ms)]

    all_segments: list[dict] = []
    time_offset = 0.0
    for chunk in chunks:
        with tempfile.NamedTemporaryFile(suffix=f".{AUDIO_FORMAT}", delete=False) as tmp:
            chunk.export(tmp.name, format="ipod", bitrate=AUDIO_BITRATE)
            with open(tmp.name, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="whisper-1", file=f,
                    response_format="verbose_json", language=language,
                    timestamp_granularities=["segment"],
                )
            for seg in result.segments:
                seg["start"] += time_offset
                seg["end"] += time_offset
                all_segments.append(seg)
            time_offset += chunk_ms / 1000.0
        os.unlink(tmp.name)
    return {"segments": all_segments, "text": " ".join(s.get("text", "") for s in all_segments)}


def transcribe_local(audio_path: str, language: str = "zh") -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper not installed. Run: pip install faster-whisper")

    # Use HF mirror in China, silent if already cached
    os.environ.setdefault("HF_ENDPOINT", HF_MIRROR)

    model_size = os.environ.get("WHISPER_MODEL", "small")
    print(f"Loading whisper model '{model_size}'...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(audio_path, language=language, beam_size=5)
    print(f"Language: {info.language} (prob: {info.language_probability:.2f})", file=sys.stderr)

    segs: list[dict] = []
    full_text: list[str] = []
    for seg in segments:
        segs.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()})
        full_text.append(seg.text.strip())
    return {"segments": segs, "text": " ".join(full_text)}


def _format_openai_result(transcription) -> dict:
    segs = [{"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
            for s in transcription.segments]
    return {"segments": segs, "text": transcription.text}


# ── Output ───────────────────────────────────────────────────────────

def format_transcript(result: dict) -> str:
    lines = []
    for seg in result["segments"]:
        m, s = divmod(int(seg["start"]), 60)
        lines.append(f"[{m}:{s:02d}] {seg['text']}")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract & transcribe video audio")
    parser.add_argument("input", help="Video file path or URL")
    parser.add_argument("--output", "-o", help="Output path (.md or .json)")
    parser.add_argument("--local", action="store_true", help="Use local faster-whisper")
    parser.add_argument("--language", default="zh", help="Language code")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--model", default="small", help="Whisper model size (tiny/small/medium/large-v3)")
    args = parser.parse_args()

    os.environ["WHISPER_MODEL"] = args.model

    ffmpeg = find_ffmpeg()
    print(f"Using ffmpeg: {ffmpeg}", file=sys.stderr)

    video_path = args.input
    if video_path.startswith(("http://", "https://")):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = download(video_path, tmpdir)
            result = _process(video_path, ffmpeg, args)
    else:
        if not Path(video_path).exists():
            sys.exit(f"File not found: {video_path}")
        result = _process(video_path, ffmpeg, args)

    if args.json:
        output = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        output = format_transcript(result)

    if args.output:
        outpath = Path(args.output)
        outpath.write_text(output, encoding="utf-8")
        print(f"\nSaved: {outpath}", file=sys.stderr)
    else:
        # Write to stdout in UTF-8, fallback file if console can't handle it
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            print(output)
        except Exception:
            outpath = Path.home() / ".cache" / "transcript_output.txt"
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_text(output, encoding="utf-8")
            print(f"Output saved to: {outpath} (console encoding issue)", file=sys.stderr)


def _process(video_path: str, ffmpeg: str, args) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / f"audio.{AUDIO_FORMAT}"
        extract_audio(video_path, str(audio_path), ffmpeg)
        if args.local:
            return transcribe_local(str(audio_path), args.language)
        else:
            return transcribe_openai(str(audio_path), args.language)


if __name__ == "__main__":
    main()
