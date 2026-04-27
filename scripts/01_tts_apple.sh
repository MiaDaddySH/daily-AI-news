#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"

PYTHON_BIN=$(resolve_python_bin)
FFMPEG_BIN=$(resolve_ffmpeg_bin)
SWIFT_BIN=$(resolve_swift_bin)

NARRATION_TEXT="output/apple_narration.txt"
OUTPUT_WAV="output/narration.wav"
OUTPUT_MP3="output/narration.mp3"
SWIFT_CACHE="${SWIFT_MODULE_CACHE_PATH:-/tmp/daily-ai-news-swift-cache}"

mkdir -p output "$SWIFT_CACHE"

"$PYTHON_BIN" - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from news_pipeline import build_narration_text, load_news_script

Path("output").mkdir(exist_ok=True)
Path("output/apple_narration.txt").write_text(build_narration_text(load_news_script()), encoding="utf-8")
PY

CLANG_MODULE_CACHE_PATH="$SWIFT_CACHE" \
  "$SWIFT_BIN" scripts/01_tts_apple.swift "$NARRATION_TEXT" "$OUTPUT_WAV" "${APPLE_TTS_VOICE_ID:-}"

"$FFMPEG_BIN" -y -i "$OUTPUT_WAV" -codec:a libmp3lame -b:a 96k "$OUTPUT_MP3" >/dev/null 2>&1

echo "Audio generated: $OUTPUT_WAV"
