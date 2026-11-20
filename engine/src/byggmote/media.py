"""ffprobe/ffmpeg wrappers. Track indices here are 0-based audio stream indices."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import replace

SR = 16000


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ffprobe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    if out.returncode:
        print(out.stderr, file=sys.stderr)  # details; the message stays one sentence
        raise RuntimeError("not an audio or video file ffmpeg can read")
    return json.loads(out.stdout)


def decodes(path: Path, track: int) -> bool:
    """Whether ffmpeg can decode audio track `track`: a tenth of a second of it. A name in ffprobe is not enough, as ffmpeg 9 names
    Apple's spatial audio (`apple_apac`) without a decoder for it (#1405)."""
    return not _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:a:{track}", "-t", "0.1", "-f", "null", "-"]).returncode


def levels(path: Path, tracks: list[int]) -> list[tuple[float, float]]:
    """(mean_db, peak_db) per audio track in `tracks`, one decode pass."""
    if not tracks:
        return []
    graph = ";".join(f"[0:a:{t}]volumedetect[v{i}]" for i, t in enumerate(tracks))
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-filter_complex", graph]
    for i in range(len(tracks)):
        cmd += ["-map", f"[v{i}]", "-f", "null", "-"]
    err = _run(cmd).stderr
    found = {}
    for m in re.finditer(r"Parsed_volumedetect_(\d+).*?(mean|max)_volume: (-?[\d.]+|-inf) dB", err):
        v = float(m[3]) if m[3] != "-inf" else -120.0
        found.setdefault(int(m[1]), {})[m[2]] = max(v, -120.0)
    return [(found.get(i, {}).get("mean", -120.0), found.get(i, {}).get("max", -120.0)) for i in range(len(tracks))]


def _ffmpeg(args: list[str], progress=None, duration: float | None = None):
    """`progress(f)`: the share of `duration` (seconds) written so far, from ffmpeg's -progress, so a long conversion moves (#1400)."""
    if not (progress and duration):
        r = _run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args])
        code, err = r.returncode, r.stderr
    else:
        # stderr to a file: a damaged file's decode errors could fill a pipe nobody reads while stdout is read, and ffmpeg would stop.
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as log, subprocess.Popen(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y", *args],
                stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", errors="replace") as p:
            try:
                for line in p.stdout:
                    k, _, v = line.strip().partition("=")
                    if k == "out_time_us" and v.isdigit():
                        progress(min(1.0, int(v) / 1e6 / duration))
            except BaseException:
                p.kill()  # Cancel (SIGTERM) stops ffmpeg too, as subprocess.run does
                raise
            code = p.wait()
            log.seek(0)
            err = log.read()
    if code:
        print(err, file=sys.stderr)
        raise RuntimeError("ffmpeg could not convert the audio")


def extract_wav(src: Path, track: int, channel: int | None, dst: Path):
    af = ["-af", f"pan=mono|c0=c{channel}"] if channel is not None else []
    _ffmpeg(["-i", str(src), "-map", f"0:a:{track}", *af, "-ac", "1", "-ar", str(SR), str(dst)])


def extract_mix(src: Path, tracks: list[int], dst: Path, progress=None, duration: float | None = None):
    if len(tracks) == 1:
        args = ["-map", f"0:a:{tracks[0]}"]
    else:
        ins = "".join(f"[0:a:{t}]" for t in tracks)
        args = ["-filter_complex", f"{ins}amix=inputs={len(tracks)}:normalize=0[m]", "-map", "[m]"]
    # A temp name, then rename: the app never opens a half-written file (#699).
    tmp = dst.with_suffix(".part" + dst.suffix)
    try:
        _ffmpeg(["-i", str(src), *args, "-ac", "1", "-ar", str(SR), "-c:a", "aac", "-b:a", "32k", str(tmp)], progress, duration)
        replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
