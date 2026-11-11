#!/usr/bin/env bash
# Cài phụ thuộc cho skill short-video trên máy mới (macOS hoặc Linux Debian/Ubuntu).
# Dùng: bash ~/.claude/skills/short-video/setup.sh   (không cài model giọng; giọng lấy từ mp3 EverAI)
set -euo pipefail

if [[ "$(uname)" == "Darwin" ]]; then
  command -v brew >/dev/null || { echo "Cần Homebrew: https://brew.sh"; exit 1; }
  brew install ffmpeg-full pipx   # ffmpeg-full có libass (filter subtitles)
  brew link --overwrite ffmpeg-full 2>/dev/null || true
else
  sudo apt-get update
  # ffmpeg của apt đã có libass; fonts-noto cho đủ dấu tiếng Việt (Linux không có Avenir Next)
  sudo apt-get install -y ffmpeg pipx python3 fonts-noto-core
fi

pipx install edge-tts || pipx upgrade edge-tts


ffmpeg -hide_banner -filters 2>/dev/null | grep -q " subtitles " && echo "OK: ffmpeg có subtitles" \
  || echo "LỖI: ffmpeg thiếu libass/subtitles"
echo "Xong. Thử: python3 $(dirname "$0")/make_video.py $(dirname "$0")/example-sleep.txt /tmp/thu.mp4"
