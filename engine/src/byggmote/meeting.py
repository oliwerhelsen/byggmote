"""meeting.json and transcript.txt: load, save, edits that never touch models."""
import errno
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import WINDOWS, ArgError, areas, atomic_write, people, read_json

SCHEMA = 1


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load(d: Path) -> dict:
    p = Path(d).expanduser() / "meeting.json"
    if not p.exists():
        raise FileNotFoundError(f"no meeting.json in {d}")
    return read_json(p, "area", "speakers", "segments")


def save(d: Path, m: dict, transcript: bool = True):
    d = Path(d).expanduser()
    m["updated_at"] = now()
    atomic_write(d / "meeting.json", json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    if transcript:
        write_transcript(d, m)


def write_transcript(d: Path, m: dict):
    atomic_write(Path(d).expanduser() / "transcript.txt", render(m))


def clock(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _context(area_id: str) -> tuple[dict, dict, list[dict]]:
    """Config, the meeting's area and people. A broken config raises: never render with empty stand-ins."""
    cfg = areas.load()
    return cfg, next((a for a in cfg["areas"] if a["id"] == area_id), {}), people.load()


# transcript.txt is in the meeting's language, `sv` or else English (#457). meeting.json keeps the Swedish automatic names.
LABELS = {"sv": ("Möte", "Projekt", "Datum", "Längd", "Talare"), "en": ("Meeting", "Project", "Date", "Length", "Speakers")}
UNNAMED = "Talare "  # + N, from `run`
SKIPPED = "Okänd"  # the app's Skip Speaker (#416)
IGNORED = "Ignorerad"  # not part of the meeting: out of transcript.txt (#549)


def _speaker(name: str, lang: str) -> str:
    """Automatic names in the meeting's language."""
    n = name.removeprefix(UNNAMED)
    if lang == "sv":
        return name
    if n != name and n.isdigit():
        return "Speaker " + n
    return "Unknown" if name == SKIPPED else name


def _who(name: str, m: dict, area: dict, ps: list[dict], lang: str) -> str:
    """`- Anna: Anna Andersson, Beställare. Ekonomichef`; the full name only when it differs from `name`."""
    ids = [s["person"] for s in m["speakers"] if s["name"] == name and s.get("person")]
    p = next((p for p in ps if ids and p["id"] == ids[0]), None)
    if not p:
        return f"- {_speaker(name, lang)}"
    role = next((x.get("role") for x in area.get("people", []) if x["person"] == p["id"]), None)
    who = ", ".join(filter(None, [p["name"] if p["name"] != name else None, role]))
    about = ". ".join(filter(None, [who, p.get("note")]))
    return f"- {name}: {about}" if about else f"- {name}"


def render(m: dict) -> str:
    _, area, ps = _context(m["area"])
    lang = m.get("lang", "sv")
    lang = lang if lang in LABELS else "en"
    names = {s["id"]: s["name"] for s in m["speakers"]}
    kept = [g for g in m["segments"] if names[g["speaker"]] != IGNORED]
    used = list(dict.fromkeys(names[g["speaker"]] for g in kept))
    rec = datetime.fromisoformat(m["recorded_at"]).strftime("%Y-%m-%d %H:%M")
    meet, where, date, length, speakers = LABELS[lang]
    lines = [f"{meet}: {m['title']}", f"{where}: {areas.name(area, lang) or m['area']}", f"{date}: {rec}",
             f"{length}: {clock(m['duration'])}", f"{speakers}:", *(_who(n, m, area, ps, lang) for n in used), ""]
    said = {i: _speaker(n, lang) for i, n in names.items()}
    lines += [f"[{clock(g['start'])}] {said[g['speaker']]}: {g['text']}" for g in kept]
    return "\n".join(lines) + "\n"


def find(m: dict, ref: str) -> list[dict]:
    return [s for s in m["speakers"] if s["id"] == ref] or [s for s in m["speakers"] if s["name"] == ref]


def _person(m: dict, ref: str) -> tuple[str, str | None]:
    """(name, person id) for a person reference. Short name unless another person in the meeting has it."""
    cfg, _, ps = _context(m["area"])
    p = people.resolve(ref, cfg, m["area"], ps)
    if not p:
        return ref, None
    short = people.label(p)
    taken = any(s["name"] == short and s.get("person") not in (None, p["id"]) for s in m["speakers"])
    return (p["name"] if taken else short), p["id"]


def rename(m: dict, pairs: list[str]):
    for p in pairs:
        old, sep, new = p.partition("=")
        if not sep or not old.strip() or not new.strip():
            raise ArgError(f"expected OLD=NEW: {p}")
        hit = find(m, old.strip())
        if not hit:
            raise ValueError(f"no speaker: {old}")
        for s in hit:
            s["person"] = None
        name, pid = _person(m, new.strip())
        for s in hit:
            s["name"], s["person"] = name, pid


def reassign(m: dict, seg_id: int, ref: str):
    seg = next((g for g in m["segments"] if g["id"] == seg_id), None)
    if not seg:
        raise ValueError(f"no segment: {seg_id}")
    ref = ref.strip()
    hit = [] if ref.startswith("@") else find(m, ref)
    if not hit:
        name, pid = _person(m, ref)
        # A person's own speaker, never a free one that only has their short name.
        hit = [s for s in m["speakers"] if s.get("person") == pid] if pid else find(m, name)
    if not hit:
        n = max((int(s["id"][1:]) for s in m["speakers"]), default=0) + 1
        hit = [{"id": f"S{n}", "name": name, "person": pid, "track": None, "cluster": None, "embedding": None}]
        m["speakers"].append(hit[0])
    seg["speaker"] = hit[0]["id"]


def edit(m: dict, seg_id: int, text: str):
    """New text for a line. `words` keep the transcription (a word corrected from the vocabulary has what was heard
    in `heard`, #429); `edited` marks a line that differs from them, also one edited back to the heard form."""
    seg = next((g for g in m["segments"] if g["id"] == seg_id), None)
    if not seg:
        raise ValueError(f"no segment: {seg_id}")
    text = " ".join(text.split())
    if not text:
        raise ArgError("empty text")
    seg["text"] = text
    if text == " ".join(w["w"] for w in seg["words"]):
        seg.pop("edited", None)
    else:
        seg["edited"] = True


def set_title(m: dict, text: str):
    text = " ".join(text.split())
    if not text:
        raise ArgError("empty title")
    m["title"] = text


def mom(d: Path, m: dict) -> Path | None:
    """The minutes file in `mom`: a file in the project's own folder. One named next to its meeting is read from the meeting's own folder,
    wherever that is now."""
    if not m.get("mom"):
        return None
    *up, name = re.split(r"[\\/]", m["mom"])
    return Path(d).expanduser() / name if up and up[-1] == Path(d).expanduser().name else Path(m["mom"]).expanduser()


def minutes(d: Path, m: dict) -> Path:
    """The meeting's minutes: `mom`, else minutes.md in its folder."""
    return mom(d, m) or Path(d) / "minutes.md"


def free_dir(base: Path) -> Path:
    """`base`, or `base (2)`, `(3)`... if it already holds something."""
    d, n = base, 2
    while d.exists() and any(d.iterdir()):
        d, n = base.with_name(f"{base.name} ({n})"), n + 1
    return d


def _join(cfg: dict, area: dict, m: dict):
    """The meeting's linked people become the area's (not those in every area, not deleted people); other areas keep them."""
    ps = people.load()
    known = people.in_all_areas(cfg, ps) | {x["person"] for x in area.get("people", [])}
    ids = {p["id"] for p in ps}
    new = [pid for pid in dict.fromkeys(x.get("person") for x in m["speakers"] + m.get("tracks", []))
           if pid in ids and pid not in known]
    if new:
        area.setdefault("people", []).extend({"person": pid} for pid in new)
        areas.save(cfg)


def move(d: Path, m: dict, area_id: str) -> Path:
    """The folder into the area's transcripts folder (same name, ` (2)` if taken), `area` updated.
    The people come along first: a failed move leaves them known in the area, which is harmless."""
    cfg = areas.load()
    area = areas.get(cfg, area_id)
    if m.get("status") == "processing":
        raise ValueError("the meeting is still processing")
    _join(cfg, area, m)
    d = Path(d).expanduser()
    root = areas.transcripts(area)
    root.mkdir(parents=True, exist_ok=True)
    dst = d if d.resolve().parent == root.resolve() else free_dir(root / d.name)
    f = mom(d, m)
    if dst != d and f and f.resolve().is_relative_to(d.resolve()):
        m["mom"] = str(dst.resolve() / f.resolve().relative_to(d.resolve()))  # minutes next to the transcript move along
    if dst != d:
        if dst.exists():
            dst.rmdir()  # empty (free_dir); shutil.move would put the folder inside it
        for f in (d, d.parent) if not WINDOWS else ():  # else shutil.move copies it on Linux and can't remove the original
            if not os.access(f, os.W_OK):
                raise PermissionError(errno.EACCES, "Permission denied", str(f))
        shutil.move(d, dst)
    old, m["area"] = m.get("area"), area_id
    try:
        save(dst, m)
    except BaseException:
        if dst != d:
            shutil.move(dst, d)
        m["area"] = old  # meeting.json may have been written before transcript.txt failed
        try:
            save(d, m, transcript=False)
        except OSError:
            pass
        raise
    return dst


def everywhere(cfg: dict) -> list[tuple[Path, dict]]:
    """Every readable meeting in every area's transcripts folder, once each."""
    found = {}
    for a in cfg["areas"]:
        root = areas.transcripts(a)
        for d in sorted(root.iterdir()) if root.is_dir() else []:
            if d.resolve() not in found and (d / "meeting.json").exists():
                try:
                    found[d.resolve()] = (d, load(d))
                except (OSError, ValueError):
                    pass
    return list(found.values())


def links(m: dict, pid: str) -> bool:
    return any(x.get("person") == pid for x in m["speakers"] + m.get("tracks", []))


STATUSES = ("processing", "review", "done", "failed")
