---
name: video-transcribe
description: Extract and refine content from video files — speech-to-text via Whisper API, then AI refinement. Handles local files and URLs (B站, YouTube, etc.). Best accuracy via OpenAI Whisper API, with local fallback.
origin: custom
---

# Video Transcribe & Refine

Extract speech from video, transcribe to text, and refine into structured insights.

## Quick Start

```
# Local file
/video-transcribe path/to/video.mp4

# URL (B站, YouTube, etc.)
/video-transcribe https://www.youtube.com/watch?v=xxxxx

# With refinement focus
/video-transcribe video.mp4 --focus "investment strategy"
```

## Pipeline

```
Video → [download if URL] → Extract Audio (ffmpeg) → Transcribe (Whisper API) → Refine (Claude)
```

## One-Time Setup

```bash
# 1. Install ffmpeg (required)
winget install ffmpeg

# 2. Install Python deps (choose one transcription backend)
pip install openai yt-dlp          # OpenAI Whisper API (best accuracy)
pip install faster-whisper yt-dlp  # Local transcription (no API key needed)
```

Set `OPENAI_API_KEY` environment variable for Whisper API mode.

## Usage

### 1. Transcribe Only
Provide a video file path. The skill extracts audio and returns a timestamped transcript.

### 2. Transcribe + Refine
After transcription, Claude refines the content:
- **Summary**: Key points in 5-10 bullets
- **Deep Dive**: Full structured analysis
- **Action Items**: Extracted decisions, deadlines, numbers
- **Custom**: Pass `--focus "topic"` to target specific content

### 3. From URL
Supports YouTube, B站 (bilibili), and most video platforms via yt-dlp.

## Transcription Backends

| Backend | Accuracy | Speed | Cost | Setup |
|---------|----------|-------|------|-------|
| OpenAI Whisper API | ★★★★★ | Fast | ~$0.006/min | pip install openai |
| faster-whisper (local) | ★★★★☆ | Medium | Free | pip install faster-whisper |

## Refinement Prompts

After transcription, Claude processes the text. Specify refinement intent:

- **Financial/Earnings calls**: Extract numbers, guidance, risks, Q&A highlights
- **Market analysis**: Capture trading thesis, levels, catalysts, timeframe
- **Tutorial/Lecture**: Structured notes, key concepts, examples
- **Meeting**: Decisions, action items, owners, deadlines
- **General**: Auto-detect and summarize

## File Paths

Helper script: `~/.claude/skills/ecc/video-transcribe/transcribe.py`

## Notes

- Max video length: ~4 hours (Whisper API limit: 25MB per chunk, script handles chunking)
- Supported formats: mp4, avi, mov, mkv, webm, flv, wmv
- Timestamps are approximate (±2s accuracy)
- Local faster-whisper requires ~2GB RAM for base model, ~6GB for large model
