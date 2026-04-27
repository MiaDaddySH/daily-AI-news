#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"

INPUT_FILE="input/news_script.txt"
AIFF_FILE="output/audio.aiff"
WAV_FILE="output/audio.wav"
PYTHON_BIN=$(resolve_python_bin)
FFMPEG_BIN=$(resolve_ffmpeg_bin)
FFPROBE_BIN=$(resolve_ffprobe_bin)

mkdir -p output

# 你可以先运行 say -v '?' 查看系统可用声音
# 中文声音常见可能是 Tingting、Meijia、Sinji 等，取决于系统安装情况
VOICE="${MAC_TTS_VOICE:-Eddy (中文（中国大陆）)}"

"$PYTHON_BIN" - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from news_pipeline import build_narration_text, load_news_script

Path("output").mkdir(exist_ok=True)
Path("output/mac_narration.txt").write_text(build_narration_text(load_news_script()), encoding="utf-8")
PY

say -v "$VOICE" -f "output/mac_narration.txt" -o "$AIFF_FILE"

if afinfo "$AIFF_FILE" 2>/dev/null | grep -q "audio bytes: 0"; then
  echo "macOS say generated an empty AIFF file. Check the local voice service or try a different MAC_TTS_VOICE." >&2
  exit 1
fi

"$FFMPEG_BIN" -y -i "$AIFF_FILE" -ar 44100 -ac 2 "$WAV_FILE"

if [ "$("$FFPROBE_BIN" -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$WAV_FILE")" = "N/A" ]; then
  echo "macOS say fallback produced an invalid WAV file." >&2
  exit 1
fi

echo "Audio generated: $WAV_FILE"
