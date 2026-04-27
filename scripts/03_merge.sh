#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"

AUDIO="output/audio.wav"
BGM="input/bgm.mp3"
FRAME_LIST="output/frames.txt"
PYTHON_BIN=$(resolve_python_bin)
FFMPEG_BIN=$(resolve_ffmpeg_bin)

DATE_TEXT=$(date +"%Y-%m-%d")
FINAL="output/final_news_${DATE_TEXT}.mp4"

"$PYTHON_BIN" scripts/03_render_frames.py

if [ -f "$BGM" ]; then
  echo "Merging video with background music..."

  "$FFMPEG_BIN" -y \
    -f concat \
    -safe 0 \
    -i "$FRAME_LIST" \
    -i "$AUDIO" \
    -stream_loop -1 \
    -i "$BGM" \
    -filter_complex "[1:a]volume=1.0[a0];[2:a]volume=0.08[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
    -map 0:v \
    -map "[aout]" \
    -c:v libx264 \
    -preset medium \
    -crf 25 \
    -c:a aac \
    -b:a 192k \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -shortest \
    "$FINAL"
else
  echo "Merging video without background music..."

  "$FFMPEG_BIN" -y \
    -f concat \
    -safe 0 \
    -i "$FRAME_LIST" \
    -i "$AUDIO" \
    -c:v libx264 \
    -preset medium \
    -crf 25 \
    -c:a aac \
    -b:a 192k \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -shortest \
    "$FINAL"
fi

echo "Video generated: $FINAL"
