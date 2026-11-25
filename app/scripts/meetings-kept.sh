#!/usr/bin/env bash
# An uninstall leaves the meetings alone. `before`: the installed engine names its real default meetings folder (no
# BYGGMOTE_CONFIG, so the one a person gets) and makes a project there, and what is in the folder is noted in STATE.
# `after`, once the app is uninstalled: the folder must hold the same files.
#
#   scripts/meetings-kept.sh before <the app's resources folder> STATE
#   scripts/meetings-kept.sh after STATE
set -euo pipefail

list() { (cd "$1" && find . -type f | LC_ALL=C sort); }

case "$1" in
  before)
    R="$2/engine"
    case "$(uname -s)" in
      MINGW* | MSYS* | CYGWIN*) R=$(cygpath -u "$R"); PY="$R/python/python.exe" ;;
      *) PY="$R/python/bin/python3" ;;
    esac
    unset BYGGMOTE_CONFIG
    echo '{"name": "Kv. Prov"}' | "$PY" -m byggmote areas add >/dev/null
    folder=$("$PY" -m byggmote projects | "$PY" -c 'import json, sys; print(json.load(sys.stdin)["folder"])')
    case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) folder=$(cygpath -u "$folder") ;; esac
    mkdir -p "$folder" && echo 'a meeting' >"$folder/keep.txt"
    echo "the meetings folder: $folder"
    { echo "$folder"; list "$folder"; } >"$3"
    ;;
  after)
    folder=$(head -1 "$2")
    [ "$(tail -n +2 "$2")" = "$(list "$folder")" ] || { echo "the uninstall changed $folder"; exit 1; }
    echo "the meetings folder is as it was: $folder"
    ;;
esac
