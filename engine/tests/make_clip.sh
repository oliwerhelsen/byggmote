#!/bin/sh
# A test recording from a script of lines (`Name|text`), spoken by macOS's Swedish voice. Each name gets its own pitch, so
# the speaker model has voices to tell apart. Prints when each line starts, for the marks of a test meeting.
# Usage: make_clip.sh tests/data/byggmote5.txt out.m4a
set -eu
script=$1 out=$2
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
i=0 at=0
while IFS='|' read -r who text; do
  i=$((i + 1))
  n=$(printf '%02d' "$i")
  say -v Alva -o "$tmp/$n.aiff" "$text"
  case $who in
    Maria) pitch="anull" ;;
    Jonas) pitch="asetrate=22050*0.78,aresample=22050,atempo=1.2821" ;;
    *) pitch="asetrate=22050*0.90,aresample=22050,atempo=1.1111" ;;
  esac
  ffmpeg -loglevel error -y -i "$tmp/$n.aiff" -af "aresample=22050,$pitch,apad=pad_dur=0.7" -ar 16000 -ac 1 "$tmp/$n.wav"
  echo "file '$tmp/$n.wav'" >> "$tmp/list.txt"
  printf '%s\t%s\t%s\n' "$at" "$who" "$text"
  at=$(echo "$at + $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$tmp/$n.wav")" | bc)
done < "$script"
ffmpeg -loglevel error -y -f concat -safe 0 -i "$tmp/list.txt" -c:a aac -b:a 96k "$out"
