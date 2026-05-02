#!/bin/bash
set -e

source "$(dirname "$0")/shell_common.sh"
PYTHON_BIN=$(resolve_python_bin)

echo "Generate language shorts (English/German)"
"$PYTHON_BIN" scripts/05_generate_language_shorts.py
