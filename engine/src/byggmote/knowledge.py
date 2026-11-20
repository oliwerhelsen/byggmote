"""Byggmöte's folder, the knowledge base (#817): where it is, an older config moved into it, and its guides (docs/SPEC.md)."""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from . import APP, CONFIG_NAME, LINUX, OWN_INSTRUCTIONS, ArgError, atomic_write, read_json, xdg

FILES = ("areas.json", "people.json", "learning.json")
OLD = FILES[:2]  # what an older config kept in $CONFIG
# The first line of a guide Byggmöte writes and keeps current; a file without it is the user's.
MARK = f"<!-- Written by {APP}"
KNOWS = f"## What {APP} knows"


def config_dir() -> Path:
    if c := os.environ.get("BYGGMOTE_CONFIG"):
        return Path(c).expanduser()
    if LINUX:
        return xdg("XDG_CONFIG_HOME", "~/.config") / CONFIG_NAME
    return Path(f"~/.config/{CONFIG_NAME}").expanduser()


def pointer() -> Path:
    return config_dir() / f"{CONFIG_NAME}.json"


def default() -> Path:
    from .areas import base
    return Path(base()).expanduser()


def folder() -> Path:
    """`byggmote.json`'s folder, else the default."""
    p = pointer()
    return Path(read_json(p, "folder")["folder"]).expanduser() if p.exists() else default()


def tilde(p: Path) -> str:
    """With `/` on every OS: it goes in byggmote.json and in guides an agent reads."""
    home = Path.home()
    return f"~/{p.relative_to(home).as_posix()}" if p.is_relative_to(home) else p.as_posix()


def _point(to: Path):
    pointer().parent.mkdir(parents=True, exist_ok=True)
    atomic_write(pointer(), json.dumps({"folder": tilde(to)}, ensure_ascii=False) + "\n")


def _target(old: dict) -> Path:
    """Where an older config goes: its `workspace`, else the folder of its default area's `…/default` folder, or that folder
    itself when it has another name (the oldest installs: `~/transcripts`), else the default. Never the home folder or a
    disk's root. Under BYGGMOTE_CONFIG only a folder inside it, so a copied config never writes in the real folders."""
    from . import areas
    fallback = next((a for a in old.get("areas", []) if isinstance(a, dict) and a.get("id") == areas.DEFAULT), None)
    meetings = fallback and areas.transcripts(fallback)
    c, home = config_dir().absolute(), Path.home().absolute()
    for x in (old.get("workspace"), meetings and str(meetings.parent if meetings.name == areas.DEFAULT else meetings)):
        if not isinstance(x, str) or not x.strip():
            continue
        p = Path(x).expanduser().absolute()
        if p in (c, home) or p == p.parent or "BYGGMOTE_CONFIG" in os.environ and not p.is_relative_to(c):
            continue
        return p
    return default()


def _aside(f: Path):
    """`areas.json` → `areas.json.migrated` (`.migrated.2`, … if taken): kept, never removed."""
    to, n = f.with_name(f.name + ".migrated"), 1
    while to.exists():
        n += 1
        to = f.with_name(f"{f.name}.migrated.{n}")
    os.rename(f, to)


@contextmanager
def locked(d: Path):
    """One engine at a time: the app starts several at once."""
    try:
        import fcntl
    except ImportError:  # Windows: no flock, a byte of a lock file instead
        yield from _locked_windows(d)
        return
    fd = os.open(d, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _locked_windows(d: Path):
    import msvcrt
    with open(d / ".byggmote.lock", "a+b") as f:
        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.05)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def migrate():
    """An older config ($CONFIG/areas.json, people.json) into Byggmöte's folder. Each step reruns safely: a file already in
    the folder wins, the pointer comes after the copies, the old files are renamed last. A broken file, here or in the
    folder, stops it unmoved."""
    c = config_dir()
    if not any((c / n).exists() for n in OLD):
        return
    if pointer().exists() and folder().absolute() == c.absolute():  # before the lock: a command holding it here would wait on itself
        return
    with locked(c):
        old = [c / n for n in OLD if (c / n).exists()]  # another engine may have moved them while this one waited
        if not old:
            return
        texts = {f.name: f.read_text(encoding="utf-8") for f in old}
        cfg = read_json(c / "areas.json", "areas") if "areas.json" in texts else {}
        if "people.json" in texts:
            read_json(c / "people.json", "people")
        pointed = pointer().exists()
        dest = folder() if pointed else _target(cfg)
        if pointed and not dest.is_dir():  # renamed or not mounted: areas.load says so, nothing is made there
            return
        if dest.absolute() == c.absolute():  # Byggmöte's folder is the config folder: nothing to move
            return
        for name in texts:
            if (dest / name).exists():  # it wins only if Byggmöte can read it
                read_json(dest / name, name.removesuffix(".json"))
        dest.mkdir(parents=True, exist_ok=True)
        for name, text in texts.items():
            if (dest / name).exists():
                continue
            if name == "areas.json" and "workspace" in cfg:  # the workspace is the folder now
                text = json.dumps({k: v for k, v in cfg.items() if k != "workspace"}, ensure_ascii=False, indent=2) + "\n"
            atomic_write(dest / name, text)
        if not pointed:
            _point(dest)
        for f in old:
            _aside(f)


def _new_knows(root: Path, old: Path):
    """Byggmöte's own guide whose "What Byggmöte knows" still names the old config gets the new section; nothing else changes."""
    g = root / "AGENTS.md"
    try:
        text = g.read_text(encoding="utf-8")
    except OSError:
        return
    start = text.find(KNOWS)
    if not text.startswith(f"# {APP} workspace") or start < 0:
        return
    end = text.find("\n## ", start + len(KNOWS))
    end = len(text) if end < 0 else end + 1
    if not any(p in text[start:end] for p in (str(old / "areas.json"), tilde(old / "areas.json"))):
        return
    atomic_write(g, text[:start] + KNOWS_TEXT + ("\n" if end < len(text) else "") + text[end:])


def move_to(path: Path) -> Path:
    """`byggmote folder PATH`: a folder with `areas.json` is used as it is; one without any of the files gets them moved.
    Copies first, then the pointer, then the old files go: interrupted, the old folder still has everything. A folder
    with only some of them, or one Byggmöte can't read, stops it unmoved."""
    from . import areas
    cur = folder().absolute()
    here = cur.is_dir()  # a missing folder has nothing to move
    if here:
        try:
            areas.load()
        except PermissionError:  # nor one macOS doesn't let Byggmöte open (#1232): its stat works, its files don't
            here = False
    to = path.expanduser().absolute()
    same = here and to.exists() and to.resolve() == cur.resolve()
    there = [] if same else [n for n in FILES if (to / n).exists()]
    if there and "areas.json" not in there:
        raise ArgError(f"{tilde(to)} has {', '.join(there)} but no areas.json")
    for n in OLD:
        if n in there:
            read_json(to / n, n.removesuffix(".json"))
    to.mkdir(parents=True, exist_ok=True)
    moved = []
    if here and not there and not same:
        for n in FILES:
            if (cur / n).exists():
                atomic_write(to / n, (cur / n).read_text(encoding="utf-8"))
                moved.append(cur / n)
    _point(to)
    for f in moved:
        f.unlink()
    if moved:
        _leave(cur)
    guides(areas.load(), force=True)
    return to


def _leave(d: Path):
    """The folder the knowledge base left: Byggmöte's guide goes if nobody changed it, and the folder if that left it empty
    (a new install's default before the folder chosen in onboarding)."""
    try:
        if (d / "AGENTS.md").read_text(encoding="utf-8") == GUIDE and os.readlink(d / "CLAUDE.md") == "AGENTS.md":
            (d / "CLAUDE.md").unlink()
            (d / "AGENTS.md").unlink()
            d.rmdir()
    except OSError:
        pass


_written: tuple | None = None


def guides(cfg: dict, force: bool = False):
    """Byggmöte's folder's guide when it has none, and each existing area folder's AGENTS.md, Byggmöte's own rewritten when
    stale. Once per change of folder and areas in a process. A folder Byggmöte can't write in stops nothing."""
    global _written
    root = folder()
    key = (str(root), json.dumps([[a.get("id"), a.get("name"), a.get("transcripts")] for a in cfg.get("areas", [])]))
    if key == _written and not force:
        return
    _written = key
    try:
        if root.is_dir() and not any((root / n).exists() or (root / n).is_symlink() for n in ("AGENTS.md", "CLAUDE.md")):
            atomic_write(root / "AGENTS.md", GUIDE)
            try:
                os.symlink("AGENTS.md", root / "CLAUDE.md")
            except OSError:  # Windows without developer mode: an import instead of a link
                atomic_write(root / "CLAUDE.md", "@AGENTS.md\n")
        _new_knows(root, config_dir())
    except OSError:
        pass
    from . import areas
    for a in cfg.get("areas", []):
        d = areas.transcripts(a)
        f = d / "AGENTS.md"
        try:
            if not d.is_dir() or areas.shared(d) is not None or (f.exists() or f.is_symlink()) and not f.read_text(encoding="utf-8").startswith(MARK):
                continue
            text = area_guide(a, d, root)
            if not f.exists() or f.read_text(encoding="utf-8") != text:
                atomic_write(f, text)
        except (OSError, UnicodeDecodeError):
            pass


def area_guide(a: dict, d: Path, root: Path) -> str:
    """What an agent started in the area's folder needs to find its people and terms: paths relative to the folder,
    or with `~` when the folder is outside Byggmöte's folder."""
    from . import areas
    inside = d.absolute().is_relative_to(root.absolute())
    at = lambda n: Path(os.path.relpath(root.absolute() / n, d.absolute())).as_posix() if inside else tilde(root.absolute() / n)
    name, aid = areas.name(a, a.get("lang") if a.get("lang") in areas.NO_AREA else "sv"), a["id"]
    return f"""{MARK}, which keeps it current. Your own notes about the area go in README.md. -->
# {name}

This folder is the area {name} (`{aid}`) in {APP}'s knowledge base. Each subfolder is a meeting: `transcript.txt` with the speakers at the top, `meeting.json` ({APP}'s record; edit it in {APP}) and the minutes, `minutes.md` or the file its `mom` names in the area's summaries folder.

## Who is who, and what the words mean

- `{at("people.json")}`: everyone {APP} knows, by `id`, with `name`, `short` name and a `note`.
- `{at("areas.json")}`, the area with `"id": "{aid}"`: its `people` (by `id`, with their `role` here) and its names and terms (`vocabulary`). People with `"all_areas": true` and `me` (the user) belong here too, and the `vocabulary` at the top of the file applies here as well.
- A name or term is written `Term`, or `Term = heard, heard`: the right spelling, then how speech recognition often hears it.
- `{at("learning.json")}`: what {APP} learned from each meeting, and the suggestions waiting for the user.
- `{at("AGENTS.md")}`: how the whole knowledge base is laid out.
"""


KNOWS_TEXT = f"""{KNOWS}

The people, names and terms {APP} knows are plain files in this folder. Read them for who is who and how names are spelled; change them in {APP}.

- `areas.json`: the areas. Each has an `id`, a `name`, its meetings folder (`transcripts`), where its minutes go when not with the meetings (`brain`, with `mom_dir` inside it), its `people` with their role there, and its names and terms (`vocabulary`, as `Term` or `Term = how it sounds`). The `vocabulary` at the top applies to every area; `me` is the person using {APP}. `notes` at the top, when there, is the folder that holds a folder per project for their minutes (`<notes>/<id>/meetings`).
- `people.json`: everyone, by `id`, with `name`, `short` name and a `note`.
- `learning.json`: what {APP} learned from each meeting, and the suggestions waiting for you.
- `<area>/AGENTS.md`: the same pointers, for an agent started in an area's folder.
"""

OWN_LINE = f"\n- `summary-instructions.md`: your own rules for the minutes, added after {APP}'s and winning where they differ." if OWN_INSTRUCTIONS else ""
GUIDE = f"""# {APP} workspace

This folder is {APP}'s knowledge base: every meeting and its transcript, one folder per area, and the people, names and terms {APP} has learned. Any agent can read it.

## Layout

- `<area>/`: one folder per area, such as a customer, project or team.
- `<area>/README.md`: what the area is about, its people and roles, standing notes and confidentiality. Keep it current.
- `<area>/<YYYY-MM-DD HHMM title>/`: one meeting. `transcript.txt` is the raw transcript with the speaker list at the top, `meeting.json` is {APP}'s record, `minutes.md` the minutes, or the file its `mom` names.
- `default/`: meetings not yet sorted into an area.
- Other files in an area folder (briefings, specs, decisions) are context too.{OWN_LINE}

## Conventions

- Only {APP} writes `meeting.json`, `transcript.txt` and the `.json` files here; change them in {APP}.

{KNOWS_TEXT}"""
