"""File inspection: source kind, tracks, levels, suggested track roles."""
import re
from datetime import datetime
from pathlib import Path

from . import media

OBS_NAMES = ["mix", "mic", "others"]
BYGGMOTE_NAMES = (["Mic"], ["Mic", "Others"])  # Byggmöte's own recording, named by the app: in the room, or a call
OBS_FILE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d)-(\d\d)-(\d\d)\.(mov|mkv|mp4)$")
STAMPED = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d)-(\d\d)-(\d\d)\.(mov|mkv|mp4|m4a)$")  # OBS's and Byggmöte's: the start
GENERIC = re.compile(r"^(SoundHandler|Core Media Audio|ISO Media file.*|\w*_recording\d*)?$")
SILENT_PEAK_DB = -50.0


def _name(tags: dict) -> str | None:
    for k in ("title", "name", "handler_name"):
        v = (tags.get(k) or "").strip()
        if v and not GENERIC.match(v):
            return v
    return None


def _source(path: Path, fmt_tags: dict, streams: list[dict], names: list) -> str:
    if "VoiceMemos" in fmt_tags.get("encoder", "") or "VoiceMemos" in str(path):
        return "voice-memo"
    if names in BYGGMOTE_NAMES:
        return "byggmote"
    obs_tag = any(re.search(r"_recording\d*$", s.get("tags", {}).get("name", "")) for s in streams)
    obs_names = path.suffix.lower() == ".mov" and [(n or "").lower() for n in names] == OBS_NAMES
    if OBS_FILE.match(path.name) or obs_tag or obs_names:
        return "obs"
    return "other"


def _recorded_at(path: Path, fmt_tags: dict, streams: list[dict]) -> str:
    ct = fmt_tags.get("creation_time") or next((s["tags"]["creation_time"] for s in streams
                                                 if s.get("tags", {}).get("creation_time")), None)
    if ct:
        try:
            return datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone().isoformat(timespec="seconds")
        except ValueError:  # some recorders write zeros
            pass
    if m := STAMPED.match(path.name):
        return datetime.fromisoformat(f"{m[1]}T{m[2]}:{m[3]}:{m[4]}").astimezone().isoformat(timespec="seconds")
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def suggest(source: str, tracks: list[dict], me: str | None) -> dict[str, str]:
    """Without `me` (a new config) OBS's Mic track is split like any other. Byggmöte's own Mic is always split, and the voice match
    names you there (#1148)."""
    if source == "obs" and [t["id"] for t in tracks] == ["1", "2", "3"]:  # not with a track left out (#1405)
        roles = {"1": "skip", "2": f"@{me}" if me else "split", "3": "split"}
    else:
        roles = {t["id"]: "split" for t in tracks}
    if not all(t["silent"] for t in tracks):
        roles |= {t["id"]: "skip" for t in tracks if t["silent"]}
    return roles


def _stream_duration(s: dict) -> float | None:
    if s.get("duration"):
        return float(s["duration"])
    if d := s.get("tags", {}).get("DURATION"):  # mkv: "00:12:34.500000000"
        h, m, sec = d.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    return None


def _duration(fmt: dict, audio: list[dict]) -> float:
    """Longest audio stream; the container can be longer (OBS video outlasting the audio)."""
    ds = [d for s in audio if (d := _stream_duration(s)) is not None]
    return round(max(ds) if ds else float(fmt.get("duration", 0)), 2)


def probe(path: Path, me: str | None) -> dict:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    info = media.ffprobe(path)
    fmt, streams = info["format"], info["streams"]
    fmt_tags = fmt.get("tags", {})
    # A track ffmpeg cannot decode (Apple's spatial audio, `apac`, next to the AAC track in an iPhone recording) is left out, as one would
    # stop every decode of the file (#1405). The id stays the stream's place, so `--track` and `0:a:N` still agree.
    every = [s for s in streams if s["codec_type"] == "audio"]
    ok = [i for i, s in enumerate(every) if s.get("codec_name") and media.decodes(path, i)]
    audio = [(i, every[i]) for i in ok]
    if not audio:
        raise ValueError(f"no audio tracks: {path}")
    lv = media.levels(path, [i for i, _ in audio])
    tracks = [{"id": str(i + 1), "name": _name(s.get("tags", {})), "codec": s.get("codec_name"),
               "channels": s.get("channels", 1), "mean_db": round(v[0], 1), "peak_db": round(v[1], 1),
               "silent": v[1] < SILENT_PEAK_DB} for (i, s), v in zip(audio, lv)]
    source = _source(path, fmt_tags, streams, [t["name"] for t in tracks])
    return {
        "path": str(path),
        "container": path.suffix.lstrip(".").lower(),
        "duration": _duration(fmt, [s for _, s in audio]),
        "size": path.stat().st_size,
        "video": any(s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")
                     for s in streams),
        "recorded_at": _recorded_at(path, fmt_tags, streams),
        "source": source,
        "title": fmt_tags.get("title"),
        "tracks": tracks,
        "unreadable": [str(i + 1) for i in range(len(every)) if i not in ok],
        "suggested": suggest(source, tracks, me),
    }
