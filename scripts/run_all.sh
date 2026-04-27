#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"

PYTHON_BIN=$(resolve_python_bin)

echo "Step 0: Preflight checks"
"$PYTHON_BIN" scripts/preflight.py

echo "Step 1: Generate narration"
if "$PYTHON_BIN" scripts/01_tts_edge.py; then
  echo "Edge TTS finished"
elif [ "${ENABLE_EXPERIMENTAL_LOCAL_TTS:-0}" = "1" ] && ./scripts/01_tts_apple.sh; then
  echo "Apple AVFoundation TTS finished"
else
  echo "TTS failed"
  exit 1
fi

echo "Step 2: Add intro and outro silence"
"$PYTHON_BIN" scripts/02_pad_audio.py

echo "Step 3: Render frames and merge video"
./scripts/03_merge.sh

echo "Done"
