#!/usr/bin/env bash
# Puts the engine and what it runs into app/engine-bundle/, which the installer carries as resources/engine:
#
#   python/   a standalone Python (python-build-standalone, through uv) with the engine and its locked packages in it
#   bin/      ffmpeg and ffprobe, and llama-server on Windows and Linux, each a pinned build checked by its checksum
#   models/   the Mac's speaker model, when there is one to ship (README.md: it is gated where it is published)
#
# Nothing is expected on the user's path: the app starts this Python and puts bin/ first on the engine's PATH.
# Run from app/ with uv on the path, in CI (.github/workflows/release.yml) or on a developer's computer.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=engine-bundle
DL=engine-bundle-downloads
ENGINE=../engine
PYTHON=3.12

# Pinned builds. A new one is a change here, with its checksum, checked like code.
LLAMA=b12590
FFMPEG_BTBN=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-11-24-12-41
FFMPEG_BTBN_NAME=ffmpeg-n9.0.2-963-g4d831360c9
FFMPEG_MAC=https://ffmpeg.martin-riedl.de/download/macos/arm64/1795207104_9.1

case "$(uname -s)" in
  Linux) OS=linux ;;
  Darwin) OS=mac ;;
  MINGW* | MSYS* | CYGWIN*) OS=windows ;;
  *) echo "unknown system: $(uname -s)" >&2; exit 1 ;;
esac

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

# fetch URL FILE SHA256: once into the downloads folder, and refused when the checksum differs.
fetch() {
  [ -f "$DL/$2" ] || curl -sSfL -o "$DL/$2" "$1"
  local got
  got=$(sha "$DL/$2")
  if [ "$got" != "$3" ]; then
    echo "$2: checksum $got, expected $3" >&2
    rm -f "$DL/$2"
    exit 1
  fi
}

rm -rf "$OUT"
mkdir -p "$OUT/bin" "$OUT/licenses" "$DL"

# Python and the engine. uv's managed Python is relocatable, so it runs from wherever the installer puts it.
uv python install "$PYTHON" --install-dir "$OUT/python-root" --no-bin
# cpython-3.12.N-…, not the cpython-3.12-… link uv puts next to it
root=$(ls -d "$OUT"/python-root/cpython-"$PYTHON".*)
mv "$root" "$OUT/python"
rm -rf "$OUT/python-root"
if [ "$OS" = windows ]; then PY="$OUT/python/python.exe"; else PY="$OUT/python/bin/python3"; fi
extra=()
[ "$OS" = mac ] && extra=(--extra local-model) # MLX's language model, the Mac's default
uv export --project "$ENGINE" --locked --no-dev --no-emit-project --no-hashes "${extra[@]}" -o "$DL/requirements.txt" >/dev/null
uv pip install --python "$PY" --break-system-packages --link-mode copy --compile-bytecode -r "$DL/requirements.txt"
uv pip install --python "$PY" --break-system-packages --link-mode copy --compile-bytecode --no-deps "$ENGINE"
"$PY" -m byggmote version

# ffmpeg and ffprobe. LGPL builds on Windows and Linux; the Mac's are GPL builds (NOTICE.md).
case "$OS" in
  windows)
    fetch "$FFMPEG_BTBN/$FFMPEG_BTBN_NAME-win64-lgpl-9.0.zip" ffmpeg-win.zip 4eac755f025785c71ae3fc3fe7b531d59bc058de8f3173917f043f7f31e4aa97
    unzip -q -o "$DL/ffmpeg-win.zip" -d "$DL"
    cp "$DL/$FFMPEG_BTBN_NAME-win64-lgpl-9.0/bin/"{ffmpeg,ffprobe}.exe "$OUT/bin/"
    cp "$DL/$FFMPEG_BTBN_NAME-win64-lgpl-9.0/LICENSE.txt" "$OUT/licenses/ffmpeg.txt"
    ;;
  linux)
    fetch "$FFMPEG_BTBN/$FFMPEG_BTBN_NAME-linux64-lgpl-9.0.tar.xz" ffmpeg-linux.tar.xz 75b1a510465a1b07e309883da7553438aa05009f415148b3f230292f18431102
    tar -xJf "$DL/ffmpeg-linux.tar.xz" -C "$DL"
    cp "$DL/$FFMPEG_BTBN_NAME-linux64-lgpl-9.0/bin/"{ffmpeg,ffprobe} "$OUT/bin/"
    cp "$DL/$FFMPEG_BTBN_NAME-linux64-lgpl-9.0/LICENSE.txt" "$OUT/licenses/ffmpeg.txt"
    ;;
  mac)
    fetch "$FFMPEG_MAC/ffmpeg.zip" ffmpeg-mac.zip 1f66e9a690a7f1c9e60b012379f8869c11818d1797f45b21dbb2f2564ba61ae1
    fetch "$FFMPEG_MAC/ffprobe.zip" ffprobe-mac.zip 6ef2df5f575042923a28537ab37adf936f28bf3e7b85de23a1447ed447ec1dbd
    unzip -q -o "$DL/ffmpeg-mac.zip" -d "$OUT/bin"
    unzip -q -o "$DL/ffprobe-mac.zip" -d "$OUT/bin"
    printf 'ffmpeg and ffprobe built by Martin Riedl (https://ffmpeg.martin-riedl.de), GPL 3.0.\nSource: https://ffmpeg.org/download.html\n' >"$OUT/licenses/ffmpeg.txt"
    ;;
esac

# llama.cpp's server for the language model on Windows and Linux, the same build the tests run (test.yml).
case "$OS" in
  windows)
    fetch "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA/llama-$LLAMA-bin-win-cpu-x64.zip" llama-win.zip e895687489ceed01770fd5101ac377ad77ed41b5b2b7dafc8e1e1bfca613ba62
    mkdir -p "$OUT/bin/llama" && unzip -q -o "$DL/llama-win.zip" -d "$OUT/bin/llama"
    ;;
  linux)
    fetch "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA/llama-$LLAMA-bin-ubuntu-x64.tar.gz" llama-linux.tar.gz 1d3496a307edd845e206e7265c132f4229a9fdcd2113da677819b18bebf5abbd
    mkdir -p "$OUT/bin/llama" && tar -xzf "$DL/llama-linux.tar.gz" -C "$OUT/bin/llama"
    ;;
esac
if [ "$OS" != mac ]; then
  server=$(find "$OUT/bin/llama" -name 'llama-server*' -type f | head -1)
  [ -n "$server" ] || { echo "no llama-server in the build" >&2; exit 1; }
  curl -sSfL -o "$OUT/licenses/llama.cpp.txt" "https://raw.githubusercontent.com/ggml-org/llama.cpp/$LLAMA/LICENSE"
fi

# The Mac's speaker model: from the development checkout, or fetched with a Hugging Face token that has accepted its terms.
if [ "$OS" = mac ]; then
  if [ -d "$ENGINE/models/pyannote-community-1" ]; then
    mkdir -p "$OUT/models" && cp -R "$ENGINE/models/pyannote-community-1" "$OUT/models/"
  elif [ -n "${HF_TOKEN:-}" ]; then
    "$PY" -c 'import sys; from huggingface_hub import snapshot_download; snapshot_download("pyannote/speaker-diarization-community-1", revision="3533c8cf8e369892e6b79ff1bf80f7b0286a54ee", local_dir=sys.argv[1])' "$OUT/models/pyannote-community-1"
  else
    echo "warning: no speaker model for the Mac (engine/models/pyannote-community-1 or HF_TOKEN): this build cannot tell speakers apart" >&2
  fi
fi

"$OUT/bin/ffmpeg" -version | head -1
du -sh "$OUT"
