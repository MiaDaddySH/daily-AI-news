#!/bin/bash

resolve_python_bin() {
  if [ -n "${PYTHON_BIN:-}" ] && [ -x "${PYTHON_BIN}" ]; then
    echo "${PYTHON_BIN}"
    return
  fi

  if [ -x ".venv/bin/python" ]; then
    echo ".venv/bin/python"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  echo "python3 not found" >&2
  exit 1
}

resolve_ffmpeg_bin() {
  if [ -n "${FFMPEG_BIN:-}" ] && [ -x "${FFMPEG_BIN}" ]; then
    echo "${FFMPEG_BIN}"
    return
  fi

  if command -v ffmpeg >/dev/null 2>&1; then
    command -v ffmpeg
    return
  fi

  for candidate in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
    if [ -x "${candidate}" ]; then
      echo "${candidate}"
      return
    fi
  done

  echo "ffmpeg not found" >&2
  exit 1
}

resolve_ffprobe_bin() {
  if [ -n "${FFPROBE_BIN:-}" ] && [ -x "${FFPROBE_BIN}" ]; then
    echo "${FFPROBE_BIN}"
    return
  fi

  if command -v ffprobe >/dev/null 2>&1; then
    command -v ffprobe
    return
  fi

  for candidate in /opt/homebrew/bin/ffprobe /usr/local/bin/ffprobe; do
    if [ -x "${candidate}" ]; then
      echo "${candidate}"
      return
    fi
  done

  echo "ffprobe not found" >&2
  exit 1
}

resolve_swift_bin() {
  if [ -n "${SWIFT_BIN:-}" ] && [ -x "${SWIFT_BIN}" ]; then
    echo "${SWIFT_BIN}"
    return
  fi

  if command -v swift >/dev/null 2>&1; then
    command -v swift
    return
  fi

  echo "swift not found" >&2
  exit 1
}
