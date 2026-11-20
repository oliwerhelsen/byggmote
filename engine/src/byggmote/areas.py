"""areas.json in Byggmöte's folder (knowledge.py). BYGGMOTE_CONFIG overrides the config directory (tests)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import APP, FOLDER, LINUX, WINDOWS, atomic_write, read_json, xdg

DEFAULT = "default"
# The fallback area's name in transcript.txt, by the meeting's language (#457); the app shows it in the app language.
NO_AREA = {"sv": "Inget projekt", "en": "No Project"}


class FolderMissing(ValueError):
    """byggmote.json names a folder that is not there: renamed, moved or not mounted (#817)."""


def path() -> Path:
    from . import knowledge
    return knowledge.folder() / "areas.json"


def base(legacy: bool = False) -> str:
    """Parent of area folders in a new config. `legacy`: for an area without `transcripts` (only in old configs).
    Next to a BYGGMOTE_CONFIG test config so tests never write in the real folders."""
    if c := os.environ.get("BYGGMOTE_CONFIG"):
        return f"{c}/transcripts"
    return "~/transcripts" if legacy else f"{documents()}/{FOLDER}"


def documents() -> str:
    """The Documents folder. Windows: where the shell has it, often moved to OneDrive on office computers.
    Linux: XDG_DOCUMENTS_DIR in user-dirs.dirs, as xdg-user-dir reads it, else ~/Documents as Chromium has it."""
    if LINUX:
        try:
            lines = (xdg("XDG_CONFIG_HOME", "~/.config") / "user-dirs.dirs").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            k, _, v = line.partition("=")
            if k.strip() == "XDG_DOCUMENTS_DIR" and (v := v.strip().strip('"')):
                return v.replace("$HOME", "~", 1)
        return "~/Documents"
    if WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                return os.path.expandvars(winreg.QueryValueEx(k, "Personal")[0])
        except OSError:
            pass
    return "~/Documents"


def _full() -> str:
    """The account's full name."""
    if WINDOWS:
        import ctypes
        buf, n = ctypes.create_unicode_buffer(256), ctypes.c_ulong(256)
        ok = ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(n))  # NameDisplay; none for a local account
        return ok and buf.value.strip() or "Jag"
    if LINUX:  # GECOS: "Full Name,room,phone,…"
        import pwd
        try:
            return pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip() or "Jag"
        except KeyError:  # no passwd entry (a container's --user)
            return "Jag"
    return subprocess.run(["id", "-F"], capture_output=True, text=True).stdout.strip() or "Jag"


def _write(p: Path, obj: dict):
    atomic_write(p, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _me(me: str) -> dict:
    """The person for `me` when people.json is gone: an id since 0.2 (`tim`), before that a name (`Tim`).
    The account's full name when it matches, else the id as words."""
    from . import people
    pid, full = people.slug(me), _full()
    if pid in (people.slug(full), people.slug(full.split()[0])):
        return {"id": pid, "name": full} | ({"short": full.split()[0]} if " " in full else {})
    return {"id": pid, "name": me.replace("-", " ").title() if me == pid else me}


def save(cfg: dict):
    _write(path(), cfg)


def load() -> dict:
    """Moves an older config into Byggmöte's folder, creates areas.json (no `me`) and people.json if missing, and the guides.
    A broken people.json stops here, before any write."""
    from . import knowledge
    knowledge.migrate()
    cfg = _load()
    knowledge.guides(cfg)
    return cfg


def _load() -> dict:
    p, pp = path(), path().with_name("people.json")
    if pp.exists():
        read_json(pp, "people")
    if not p.exists():
        from . import knowledge
        if not p.parent.is_dir() and knowledge.pointer().exists():  # moved, renamed or not mounted: never a new, empty one
            raise FolderMissing(f"{APP}'s folder is missing: {p.parent}")
        p.parent.mkdir(parents=True, exist_ok=True)
        _write(p, {"me": None, "voices": False, "areas": [{"id": DEFAULT, "name": NO_AREA["sv"], "transcripts": f"{base()}/{DEFAULT}",
                                          "lang": "sv", "people": []}]})
    cfg = read_json(p, "areas")
    if not pp.exists():
        me = cfg.get("me")
        if not me:
            _write(pp, {"people": []})
            return cfg
        person = _me(me)
        _write(pp, {"people": [person]})
        if me != person["id"]:
            cfg["me"] = person["id"]
            _write(p, cfg)
    return cfg


def get(cfg: dict, area_id: str) -> dict:
    for a in cfg["areas"]:
        if a["id"] == area_id:
            return a
    raise ValueError(f"unknown area: {area_id}")


def name(area: dict, lang: str = "sv") -> str:
    """The fallback area is always Inget projekt/No Project, like in the app, whatever its stored name (#302)."""
    return NO_AREA[lang] if area.get("id") == DEFAULT else area.get("name", "")


def transcripts(area: dict) -> Path:
    return Path(area.get("transcripts") or f"{base(legacy=True)}/{area['id']}").expanduser()


# A project in a shared folder (#1154, #1303): its folder is one a team already shares (a Teams team's files, synced by OneDrive), marked with SHARED.

SHARED = "byggmote-area.json"


def shared(d: Path) -> dict | None:
    """The marker in a shared project's folder, or None."""
    try:
        obj = json.loads((d / SHARED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip() else None


def _mark(a: dict):
    keys = ("id", "name", "short", "lang")
    atomic_write(transcripts(a) / SHARED, json.dumps({k: a[k] for k in keys if a.get(k)}, ensure_ascii=False, indent=2) + "\n")


# Editing areas (docs/SPEC.md, Editing the knowledge base): the apps write areas.json through these, under the knowledge base's lock.

def fields(given, allowed: dict, required: tuple = ()) -> dict:
    """stdin's object, checked: `allowed` maps a field to its types; a missing required field or an empty one is an ArgError."""
    from . import ArgError
    if not isinstance(given, dict):
        raise ArgError("expected a JSON object on stdin")
    for k, v in given.items():
        if k not in allowed:
            raise ArgError(f"unknown field: {k}")
        if not isinstance(v, allowed[k]):
            raise ArgError(f"wrong type for {k}")
    for k in required:
        if not str(given.get(k) or "").strip():
            raise ArgError(f"missing {k}")
    return given


def _lang(v) -> str:
    from . import ArgError
    if v not in NO_AREA:
        raise ArgError(f"lang must be sv or en: {v}")
    return v


def _new_lang(cfg: dict) -> str:
    """A new area's language when none is given: No Area's, the one first run chose (#1275)."""
    return next((a.get("lang") for a in cfg["areas"] if a["id"] == DEFAULT and a.get("lang") in NO_AREA), "sv")


def _in_repo(d: Path) -> bool:
    return any((p / ".git").exists() for p in [d, *d.parents])


def _new_folder(cfg: dict, aid: str) -> Path:
    """Byggmöte's folder, unless it is in a git repository (audio does not belong there): then next to another area's folder."""
    from . import knowledge
    root = knowledge.folder()
    if not _in_repo(root.expanduser()):
        return root / aid
    other = next((a for a in cfg["areas"] if a["id"] != DEFAULT), None)
    if other and not _in_repo(transcripts(other).parent):
        return transcripts(other).parent / aid
    d = transcripts(get(cfg, DEFAULT)) if any(a["id"] == DEFAULT for a in cfg["areas"]) else Path(base()).expanduser() / DEFAULT
    return (d.parent if d.name == DEFAULT else d) / aid


def _readme(a: dict, people: list[dict], root: Path):
    """A README.md to fill in for an area in Byggmöte's folder, when it has none (#643)."""
    d = transcripts(a)
    f = d / "README.md"
    if not d.absolute().is_relative_to(root.absolute()) or f.exists():
        return
    names = {p["id"]: p["name"] for p in people}
    lines = [f"- {names[x['person']]}" + (f", {x['role']}" if x.get("role") else "") for x in a.get("people", []) if x["person"] in names]
    guide = next((n for n in ("AGENTS.md", "CLAUDE.md") if (root / n).exists()), "AGENTS.md")
    rel = Path(os.path.relpath(root.absolute() / guide, d.absolute())).as_posix()
    atomic_write(f, f"""# {a['name']}

What this area is about: the customer, project or team, and what you want to achieve.

## People

{chr(10).join(lines or ["- Name, role, organization"])}

## Notes

- Standing context for every meeting here: systems, terms, decisions, confidentiality.

---

{APP} keeps each meeting about {a['name']} here, in a folder of its own with the transcript. Where the people, names and terms {APP} knows here are: `AGENTS.md`. How the whole knowledge base is laid out: `{rel}`.
""")


def add(given) -> dict:
    from . import ArgError, knowledge, people
    f = fields(given, {"name": str, "lang": str, "short": (str, type(None)), "server": str}, ("name",))
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        title = " ".join(f["name"].split())
        server = (f.get("server") or "").strip()
        if server and any(a.get("server") == server for a in cfg["areas"]):
            raise ArgError(f"the server project {server} is already here")
        stem, n, taken = people.slug(server or title, "area"), 2, {a["id"] for a in cfg["areas"]}
        aid = stem
        while aid in taken:
            aid, n = f"{stem}-{n}", n + 1
        a = {"id": aid, "name": title, "transcripts": knowledge.tilde(_new_folder(cfg, aid)), "lang": _lang(f["lang"]) if "lang" in f else _new_lang(cfg),
             "people": []}
        if (f.get("short") or "").strip():
            a["short"] = f["short"].strip()
        if server:
            a["server"] = server
        elif (nf := notes(cfg)) and nf.is_dir():  # a notes folder not there (a drive not mounted, renamed): with the meetings
            _own(cfg, a, nf / aid / "meetings")
        transcripts(a).mkdir(parents=True, exist_ok=True)
        _readme(a, people.load(), knowledge.folder())
        cfg["areas"].append(a)
        save(cfg)
    knowledge.guides(cfg)
    return a


def _summaries(folder: Path, within: Path | None = None) -> tuple[str, str | None]:
    """`brain` and `mom_dir` for a summaries folder (#674): `brain` the outermost folder up from it with a README.md or a guide,
    below the nearest of the git repository's root, the knowledge base and the home folder; without one, the folder itself.
    Inside the notes folder, the project's folder directly in it (#1372)."""
    from . import knowledge
    if within and folder.is_relative_to(within) and folder != within:
        top = within / folder.relative_to(within).parts[0]
        rest = folder.relative_to(top).as_posix()
        return knowledge.tilde(top), None if rest == "." else rest
    ups = [folder, *folder.parents]
    root, home = Path(os.path.abspath(knowledge.folder())), Path(os.path.abspath(Path.home()))
    stop = next((d for d in ups if d == root or (d / ".git").exists()), home if home in ups else None)
    below = ups[:ups.index(stop)] if stop else ups[:-1]
    notes = next((d for d in reversed(below) if any((d / n).exists() for n in ("README.md", "AGENTS.md", "CLAUDE.md"))), folder)
    rest = folder.relative_to(notes).as_posix()
    return knowledge.tilde(notes), None if rest == "." else rest


def notes(cfg: dict) -> Path | None:
    """The notes folder, where each local project can have a folder for its minutes (#1372); None when not set."""
    return Path(os.path.abspath(Path(cfg["notes"]).expanduser())) if cfg.get("notes") else None


def set_notes(given) -> dict:
    """`byggmote areas notes`: the notes folder, made, or none. No area changes."""
    from . import knowledge
    f = fields(given, {"folder": (str, type(None))}, ())
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        if (f.get("folder") or "").strip():
            to = Path(os.path.abspath(Path(f["folder"].strip()).expanduser()))
            to.mkdir(parents=True, exist_ok=True)
            cfg["notes"] = knowledge.tilde(to)
        else:
            cfg.pop("notes", None)
        save(cfg)
    return {"notes": cfg.get("notes")}


def _own(cfg: dict, a: dict, to: Path) -> None:
    """The area's minutes go to `to`, made: `brain` and `mom_dir`."""
    to.mkdir(parents=True, exist_ok=True)
    a["brain"], md = _summaries(to, notes(cfg))
    a.pop("mom_dir", None)
    if md:
        a["mom_dir"] = md


def mom_folder(a: dict) -> Path | None:
    """Where the area's minutes go; None: with the meetings."""
    if not a.get("brain"):
        return None
    b = Path(a["brain"]).expanduser()
    return b / a["mom_dir"] if a.get("mom_dir") else b


def _move_summaries(cfg: dict, a: dict, old: Path | None, new: Path) -> list[str]:
    """The minutes of the area's meetings in `old` (not in `new`) to the same place under `new`; `mom` follows. `old` None: each meeting's
    minutes.md to a MOM- file in `new`, named as the app names new minutes (#1372)."""
    from . import meeting
    if old is None:
        return _move_from_meetings(cfg, a, new)
    o, nw, moved = old.resolve(), new.resolve(), []
    for d, m in meeting.everywhere(cfg):
        if m.get("area") != a["id"] or not isinstance(m.get("mom"), str):
            continue
        src = Path(m["mom"]).expanduser().resolve()
        if not src.is_relative_to(o) or src.is_relative_to(nw):
            continue
        dst = new / src.relative_to(o)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
        m["mom"] = str(dst)
        meeting.save(d, m, transcript=False)
        moved.append(str(d))
    return moved


def _move_from_meetings(cfg: dict, a: dict, new: Path) -> list[str]:
    """Each of the area's meetings with a minutes.md and no `mom`: the file to `MOM-<day>-<subject>.md` in `new`, never over a file."""
    from . import meeting
    from .people import slug
    moved = []
    for d, m in meeting.everywhere(cfg):
        src = d / "minutes.md"
        if m.get("area") != a["id"] or m.get("mom") or not src.is_file():
            continue
        base = f"MOM-{_day(d, m)}-{slug(m.get('title') or '', '')[:40].rstrip('-') or 'meeting'}"
        dst, n = new / f"{base}.md", 2
        while dst.exists():
            dst, n = new / f"{base}-{n}.md", n + 1
        new.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)
        m["mom"] = str(dst)
        meeting.save(d, m, transcript=False)
        moved.append(str(d))
    return moved


def _day(d: Path, m: dict) -> str:
    """The day the meeting was recorded, on this computer's clock, as the app dates its minutes; else the date its folder's name starts with."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(m["recorded_at"].replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except (KeyError, AttributeError, ValueError):
        return d.name[:10]


def _set_context(a: dict, aid: str, folders: list) -> None:
    """The folders the project's minutes can read, each once; none removes the field."""
    from . import ArgError, knowledge
    if folders and a.get("server"):
        raise ArgError(f"{aid} is a server project: its minutes go to the server")
    seen, kept = set(), []
    for x in folders:
        if not isinstance(x, str) or not x.strip():
            raise ArgError("context: expected a list of folders")
        p = Path(os.path.abspath(Path(x.strip()).expanduser()))
        if not p.is_dir():
            raise ArgError(f"not a folder: {x}")
        real = p.resolve()
        if real not in seen:
            seen.add(real)
            kept.append(knowledge.tilde(p))
    if kept:
        a["context"] = kept
    else:
        a.pop("context", None)


def get_known(cfg: dict, aid: str) -> dict:
    from . import ArgError
    try:
        return get(cfg, aid)
    except ValueError:
        raise ArgError(f"unknown area: {aid}") from None


def set_area(aid: str, given) -> dict:
    from . import ArgError, knowledge, people
    f = fields(given, {"name": str, "short": (str, type(None)), "lang": str, "people": list, "summaries": (str, type(None)), "context": (list, type(None)), "move": bool})
    if "name" in f and not f["name"].strip():
        raise ArgError("missing name")
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        a = get_known(cfg, aid)
        if "name" in f:
            a["name"] = " ".join(f["name"].split())
        if "short" in f:
            if (f["short"] or "").strip():
                a["short"] = f["short"].strip()
            else:
                a.pop("short", None)
        if "lang" in f:
            a["lang"] = _lang(f["lang"])
        if "people" in f:
            known, me, seen, ps = {p["id"] for p in people.load()}, cfg.get("me"), set(), []
            for x in f["people"]:
                if not isinstance(x, dict) or not isinstance(x.get("person"), str) or not isinstance(x.get("role") or "", str) \
                        or set(x) - {"person", "role"}:
                    raise ArgError("people: expected [{\"person\": ID, \"role\": TEXT}]")
                if x["person"] not in known:
                    raise ArgError(f"unknown person: {x['person']}")
                if x["person"] == me or x["person"] in seen:
                    continue
                seen.add(x["person"])
                ps.append({"person": x["person"]} | ({"role": x["role"].strip()} if (x.get("role") or "").strip() else {}))
            a["people"] = ps
        if "context" in f:
            _set_context(a, aid, f["context"] or [])
        moved, old = [], mom_folder(a)
        if "summaries" in f:
            if a.get("server") and (f["summaries"] or "").strip():
                raise ArgError(f"{aid} is a server project: its minutes go to the server")
            if (f["summaries"] or "").strip() and shared(transcripts(a)) is not None:
                raise ArgError("a shared area keeps its minutes with the meetings")
            to = Path(os.path.abspath(Path(f["summaries"].strip()).expanduser())) if (f["summaries"] or "").strip() else None
            if to is None:
                a.pop("brain", None)
                a.pop("mom_dir", None)
            elif not old or to.resolve() != old.resolve():
                _own(cfg, a, to)
                if f.get("move"):
                    save(cfg)  # the area points to the new folder before a file moves
                    moved = _move_summaries(cfg, a, old, to)
        save(cfg)
        if shared(transcripts(a)) is not None:
            _mark(a)
    knowledge.guides(cfg)
    return {"area": a, "moved": moved}


def share(aid: str, folder: str) -> dict:
    """The project's meetings and README.md move to `<folder>/<name>/`, which is marked shared and becomes the project's folder."""
    from . import ArgError, knowledge, meeting
    from .run import folder_title
    team = Path(os.path.abspath(Path(folder).expanduser()))
    if not team.is_dir():
        raise ArgError(f"not a folder: {folder}")
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        a = get_known(cfg, aid)
        if aid == DEFAULT:
            raise ArgError(f"{NO_AREA['en']} cannot be shared")
        if a.get("server"):
            raise ArgError(f"{aid} is a server project: its meetings go to the server")
        if a.get("brain"):
            raise ArgError("the area's minutes are in a folder of their own, which the team would not see")
        old = transcripts(a)
        if shared(old) is not None:
            raise ArgError(f"{a['name']} is already shared")
        mine = [(d, m) for d, m in meeting.everywhere(cfg) if d.parent.resolve() == old.resolve()]
        if any(m.get("status") == "processing" for _, m in mine):
            raise ValueError("a meeting in the project is being transcribed")
        new = meeting.free_dir(team / folder_title(a["name"]))
        new.mkdir(parents=True, exist_ok=True)
        a["transcripts"] = knowledge.tilde(new)
        _mark(a)
        save(cfg)  # the project points to the new folder before a meeting moves: an interrupted share goes on with Move to
        moved = [str(meeting.move(d, m, aid)) for d, m in mine]
        if (old / "README.md").is_file() and not (new / "README.md").exists():
            shutil.move(old / "README.md", new / "README.md")
        cfg = load()  # the moves may have added people to the project
    knowledge.guides(cfg)
    return {"area": get(cfg, aid), "moved": moved}


def join(folder: str) -> dict:
    """The shared projects in `folder` (it or its subfolders, SHARED) join areas.json; one already there stays as it is."""
    from . import ArgError, knowledge, people
    root = Path(os.path.abspath(Path(folder).expanduser()))
    if not root.is_dir():
        raise ArgError(f"not a folder: {folder}")
    found = [root] if shared(root) else sorted(d for d in root.iterdir() if d.is_dir() and shared(d))
    if not found:
        raise ValueError(f"no shared project in {root}")
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        out, added = [], []
        for d in found:
            have = next((a for a in cfg["areas"] if transcripts(a).resolve() == d.resolve()), None)
            if have:
                out.append(have)
                continue
            s, taken = shared(d), {a["id"] for a in cfg["areas"]}
            stem = s["id"] if isinstance(s.get("id"), str) and people.slug(s["id"]) == s["id"] else people.slug(s["name"], "area")
            aid, n = stem, 2
            while aid in taken:
                aid, n = f"{stem}-{n}", n + 1
            a = {"id": aid, "name": " ".join(s["name"].split()), "transcripts": knowledge.tilde(d),
                 "lang": s["lang"] if s.get("lang") in NO_AREA else _new_lang(cfg), "people": []}
            if isinstance(s.get("short"), str) and s["short"].strip():
                a["short"] = s["short"].strip()
            cfg["areas"].append(a)
            out.append(a)
            added.append(aid)
        save(cfg)
    knowledge.guides(cfg)
    return {"areas": out, "added": added}


def delete(aid: str) -> dict:
    from . import ArgError, knowledge
    with knowledge.locked(knowledge.folder()):
        cfg = load()
        if get_known(cfg, aid).get("server"):
            raise ArgError(f"{aid} is a server project: the server removes it")
        if aid == DEFAULT or len(cfg["areas"]) < 2:
            raise ArgError(f"cannot delete {aid}")
        cfg["areas"] = [a for a in cfg["areas"] if a["id"] != aid]
        save(cfg)
    return {"id": aid}
