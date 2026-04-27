import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

import edge_tts

from news_pipeline import build_narration_text, load_news_script, require_executable

OUTPUT_DIR = Path("output")
OUTPUT_MP3 = OUTPUT_DIR / "narration.mp3"
OUTPUT_WAV = OUTPUT_DIR / "narration.wav"
METADATA_PATH = OUTPUT_DIR / "tts_metadata.json"

# 常用中文声音：
# zh-CN-XiaoxiaoNeural：女声，比较自然
# zh-CN-YunxiNeural：男声，偏年轻
# zh-CN-YunjianNeural：男声，偏新闻感
VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-YunjianNeural")
RATE = os.environ.get("EDGE_TTS_RATE", "-5%")
VOLUME = os.environ.get("EDGE_TTS_VOLUME", "+0%")
PITCH = os.environ.get("EDGE_TTS_PITCH", "+0Hz")
RETRIES = int(os.environ.get("EDGE_TTS_RETRIES", "3"))


def get_audio_duration_seconds(audio_path: Path, ffprobe_bin: str) -> float:
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def build_metadata_hash(text: str) -> str:
    payload = {
        "text": text,
        "voice": VOICE,
        "rate": RATE,
        "volume": VOLUME,
        "pitch": PITCH,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def can_reuse_cached_audio(expected_hash: str, ffprobe_bin: str) -> bool:
    if not OUTPUT_WAV.exists() or not OUTPUT_MP3.exists() or not METADATA_PATH.exists():
        return False

    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        if metadata.get("content_hash") != expected_hash:
            return False
        duration = get_audio_duration_seconds(OUTPUT_WAV, ffprobe_bin)
        return duration > 1.0
    except Exception:
        return False


async def synthesize_to_mp3(text: str, target_mp3: Path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        volume=VOLUME,
        pitch=PITCH,
    )
    await communicate.save(str(target_mp3))


async def synthesize_with_retries(text: str, target_mp3: Path):
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            await synthesize_to_mp3(text, target_mp3)
            return
        except Exception as exc:
            last_error = exc
            if attempt == RETRIES:
                break
            await asyncio.sleep(min(2 * attempt, 6))

    message = str(last_error) if last_error else "unknown error"
    if "speech.platform.bing.com" in message or "ClientConnector" in message or "getaddrinfo" in message:
        raise RuntimeError(
            "Edge TTS 无法连接到远端语音服务。请确认当前运行环境允许联网，"
            "或者在有网络权限的终端里执行 ./scripts/run_all.sh。"
        ) from last_error
    raise RuntimeError(f"Edge TTS 生成失败: {message}") from last_error


def convert_mp3_to_wav(source_mp3: Path, target_wav: Path, ffmpeg_bin: str):
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            str(source_mp3),
            "-ar",
            "44100",
            "-ac",
            "2",
            str(target_wav),
        ],
        check=True,
    )


def save_metadata(content_hash: str):
    METADATA_PATH.write_text(
        json.dumps(
            {
                "provider": "edge-tts",
                "voice": VOICE,
                "rate": RATE,
                "volume": VOLUME,
                "pitch": PITCH,
                "content_hash": content_hash,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    script = load_news_script()
    ffmpeg_bin = require_executable("ffmpeg")
    ffprobe_bin = require_executable("ffprobe")
    text = build_narration_text(script)
    content_hash = build_metadata_hash(text)

    if can_reuse_cached_audio(content_hash, ffprobe_bin):
        print(f"Reusing cached narration: {OUTPUT_WAV}")
        return

    temp_mp3 = OUTPUT_DIR / "narration.tmp.mp3"
    temp_wav = OUTPUT_DIR / "narration.tmp.wav"

    for path in (temp_mp3, temp_wav):
        if path.exists():
            path.unlink()

    await synthesize_with_retries(text, temp_mp3)
    convert_mp3_to_wav(temp_mp3, temp_wav, ffmpeg_bin)

    duration = get_audio_duration_seconds(temp_wav, ffprobe_bin)
    if duration <= 1.0:
        raise RuntimeError("Edge TTS 生成的音频时长异常。")

    temp_mp3.replace(OUTPUT_MP3)
    temp_wav.replace(OUTPUT_WAV)
    save_metadata(content_hash)
    print(f"Narration generated: {OUTPUT_WAV}")


if __name__ == "__main__":
    asyncio.run(main())
