"""批量转录 B站 音频 → 文字"""
import subprocess, sys, os
from pathlib import Path

PYTHON = sys.executable
FFMPEG = r"D:\tools\ffmpeg\bin\ffmpeg.exe" if os.path.exists(r"D:\tools\ffmpeg\bin\ffmpeg.exe") else subprocess.run(["where", "ffmpeg"], capture_output=True, text=True).stdout.strip().split("\n")[0]
AUDIO_DIR = Path("D:/1989n/stock_data/bilibili_audio")
OUT_DIR = Path("D:/1989n/stock_data/bilibili_transcripts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"  [!] {r.stderr[:200]}")
    return r.returncode == 0

def transcribe_audio(audio_path, out_path):
    """用 faster-whisper 转录音频"""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), language="zh", beam_size=5)
        print(f"  语言: {info.language} (概率: {info.language_probability:.2f})")
        with open(out_path, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}\n")
        return True
    except Exception as e:
        print(f"  [!] 转录失败: {e}")
        return False

def extract_audio(video_path, audio_path):
    """从视频提取音频为 WAV"""
    cmd = [FFMPEG, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
           "-ar", "16000", "-ac", "1", str(audio_path), "-y"]
    return run(cmd, timeout=120)

def main():
    if not AUDIO_DIR.exists():
        print(f"音频目录不存在: {AUDIO_DIR}")
        return

    audio_files = sorted(AUDIO_DIR.glob("*.m4a")) + sorted(AUDIO_DIR.glob("*.mp3")) + sorted(AUDIO_DIR.glob("*.wav"))
    if not audio_files:
        print("没有找到音频文件")
        return

    print(f"找到 {len(audio_files)} 个音频文件")
    for af in audio_files:
        name = af.stem
        txt_out = OUT_DIR / f"{name}.txt"
        if txt_out.exists():
            print(f"  [SKIP] {name} - 已存在")
            continue
        print(f"  [转录] {name} ...")
        transcribe_audio(af, txt_out)
    print("完成")

if __name__ == "__main__":
    main()
