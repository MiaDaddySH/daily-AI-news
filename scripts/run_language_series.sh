#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"
PYTHON_BIN=$(resolve_python_bin)

echo "Generate language lesson series videos"
"$PYTHON_BIN" scripts/06_generate_language_series.py
