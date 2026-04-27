import subprocess
from pathlib import Path
from news_pipeline import build_subtitle_lines, load_news_script, require_executable

INPUT_AUDIO = Path("output/audio.wav")
OUTPUT_SRT = Path("output/subtitles.srt")

def get_audio_duration_seconds(audio_path: Path) -> float:
    ffprobe_bin = require_executable("ffprobe")
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())

def format_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0

    ms = int((seconds - int(seconds)) * 1000)
    total = int(seconds)
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def main():
    script = load_news_script()
    lines = build_subtitle_lines(script)

    duration = get_audio_duration_seconds(INPUT_AUDIO)

    # 根据每句字数分配时间。中文口播基本可以这样粗略估算。
    weights = [max(len(line), 6) for line in lines]
    total_weight = sum(weights)

    current = 0.0
    srt_blocks = []

    for idx, line in enumerate(lines, start=1):
        line_duration = duration * weights[idx - 1] / total_weight

        # 每条字幕最短 1.4 秒，最长 6 秒，避免闪太快或停太久
        line_duration = max(1.4, min(line_duration, 6.0))

        start = current
        end = min(current + line_duration, duration)

        srt_blocks.append(
            f"{idx}\n"
            f"{format_time(start)} --> {format_time(end)}\n"
            f"{line}\n"
        )

        current = end

        if current >= duration:
            break

    OUTPUT_SRT.write_text("\n".join(srt_blocks), encoding="utf-8")
    print(f"Subtitles generated: {OUTPUT_SRT}")

if __name__ == "__main__":
    main()
