#!/usr/bin/env bash
# The installed app's engine runs the way the app starts it (src/main/engine.ts), with nothing of the computer's on its
# path: its Python answers, it lists its models, its ffmpeg reads a recording, and llama-server starts.
#
#   scripts/smoke-installed.sh <the app's resources folder>
set -euo pipefail

R="$1/engine"
case "$(uname -s)" in
  # Git Bash's /usr/bin for this script's own tools; it has no ffmpeg or Python
  MINGW* | MSYS* | CYGWIN*) PY="$R/python/python.exe"; SYSTEM=/usr/bin:/c/Windows/System32; EXE=.exe ;;
  *) PY="$R/python/bin/python3"; SYSTEM=/usr/bin:/bin; EXE= ;;
esac
# The installed app's own bin and the operating system's, nothing a developer installed.
export PATH="$R/bin:$SYSTEM" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
BYGGMOTE_CONFIG=$(mktemp -d)
export BYGGMOTE_CONFIG
trap 'rm -rf "$BYGGMOTE_CONFIG"' EXIT

engine() { "$PY" -m byggmote "$@"; }

engine version
engine models --json | head -c 400 && echo
command -v ffmpeg ffprobe
ffmpeg -nostdin -v error -f lavfi -i "sine=frequency=440:duration=3" -ac 1 -ar 16000 "$BYGGMOTE_CONFIG/tone.m4a"
engine probe "$BYGGMOTE_CONFIG/tone.m4a" --json
if [ -d "$R/bin/llama" ]; then
  server=$(find "$R/bin/llama" -name "llama-server$EXE" -type f | head -1)
  "$server" --version
fi
echo "the installed engine runs"
