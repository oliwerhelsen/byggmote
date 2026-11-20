"""A project's meeting series and their agendas (dagordning).

A series is one kind of recurring meeting in a project: Byggmöte, Samordningsmöte. A point (punkt) is numbered
<meeting>.<heading>.<n> and follows along from meeting to meeting until one closes it, so a heading (rubrik) keeps its
number for good: it can be renamed and new ones go last, never moved or removed. `series.json` in the project's
folder has the series; the points are in each meeting's protocol.json (protocol.py)."""
import json
from pathlib import Path

from . import ArgError, areas, atomic_write, knowledge, read_json
from .people import slug

FILE = "series.json"
# A byggmöte's headings when none are given. `fill`: what the engine writes under the heading itself, where the language
# model writes no points.
BYGGMOTE = [
    {"name": "Närvarande", "hint": "Fylls i från inspelningen", "fill": "attendees"},
    {"name": "Föregående protokoll", "hint": "Justering och det som kvarstår"},
    {"name": "Tidplan", "hint": "Tidsläge, avvikelser mot tidplanen, leveranser"},
    {"name": "Ekonomi", "hint": "ÄTA, betalningsplan, mängdreglering"},
    {"name": "Handlingar", "hint": "Ritningar, revideringar, handlingar som saknas"},
    {"name": "Arbetsmiljö", "hint": "BAS-U, skyddsronder, tillbud"},
    {"name": "Kvalitet och miljö", "hint": "Egenkontroller, fukt, avfall"},
    {"name": "Hinder och störningar", "hint": "Det som försenar eller stör arbetet"},
    {"name": "Myndigheter", "hint": "Bygglov, startbesked, kontrollansvarig"},
    {"name": "Övriga frågor", "hint": "Det som inte hör hemma under en annan rubrik"},
    {"name": "Nästa möte", "hint": "Tid och plats"},
]
# Construction terms speech recognition writes as ordinary words: into the project's vocabulary with its first series.
VOCABULARY = [("ÄTA", ["äta"]), ("BAS-U", ["bas u", "basu"]), ("BAS-P", ["bas p", "basp"]),
              ("AB 04", ["ab noll fyra"]), ("ABT 06", ["abt noll sex"])]
FILLS = ("attendees",)


def path(area: dict) -> Path:
    return areas.transcripts(area) / FILE


def load(area: dict) -> dict:
    p = path(area)
    return read_json(p, "series") if p.exists() else {"series": []}


def _save(area: dict, data: dict):
    path(area).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path(area), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def get(data: dict, sid: str) -> dict:
    s = next((s for s in data["series"] if s["id"] == sid), None)
    if not s:
        raise ArgError(f"unknown series: {sid}")
    return s


def _heading(x, no: int) -> dict:
    """A heading from {"name", "hint", "fill"}, checked, with its number."""
    if not isinstance(x, dict) or set(x) - {"name", "hint", "fill"} or not isinstance(x.get("name"), str) \
            or not isinstance(x.get("hint") or "", str):
        raise ArgError("headings: expected [{\"name\": TEXT, \"hint\": TEXT}]")
    name = " ".join(x["name"].split())
    if not name:
        raise ArgError("headings: missing name")
    if x.get("fill") not in (None, *FILLS):
        raise ArgError(f"headings: unknown fill: {x['fill']}")
    h = {"no": no, "name": name}
    if (x.get("hint") or "").strip():
        h["hint"] = x["hint"].strip()
    if x.get("fill"):
        h["fill"] = x["fill"]
    return h


def start(area_id: str, given) -> dict:
    """A new series in the project from {"name", "headings"}; without headings, a byggmöte's. The project's vocabulary
    gets the construction terms it lacks."""
    from . import terms
    f = areas.fields(given, {"name": str, "headings": list}, ("name",))
    if "headings" in f and not f["headings"]:
        raise ArgError("headings: expected at least one")
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        area = areas.get_known(cfg, area_id)
        data = load(area)
        name = " ".join(f["name"].split())
        stem, n, taken = slug(name, "series"), 2, {s["id"] for s in data["series"]}
        sid = stem
        while sid in taken:
            sid, n = f"{stem}-{n}", n + 1
        s = {"id": sid, "name": name, "headings": [_heading(x, i) for i, x in enumerate(f.get("headings") or BYGGMOTE, 1)],
             "meetings": []}
        data["series"].append(s)
        _save(area, data)
        had = list(area.get("vocabulary") or [])
        for term, heard in VOCABULARY:
            terms._put(area, term, heard)
        if area.get("vocabulary") != had:
            areas.save(cfg)
    return s


def heading(area_id: str, sid: str, given) -> dict:
    """{"no", "name", "hint"} renames heading `no`; without `no`, a new heading with the next number. Nothing else: a
    point's number names its heading."""
    f = areas.fields(given, {"no": int, "name": str, "hint": (str, type(None))}, ("name",))
    with knowledge.locked(knowledge.folder()):
        area = areas.get_known(areas.load(), area_id)
        data = load(area)
        s = get(data, sid)
        if "no" in f:
            h = next((h for h in s["headings"] if h["no"] == f["no"]), None)
            if not h:
                raise ArgError(f"no heading {f['no']}")
            new = _heading({"name": f["name"], "hint": f["hint"] if "hint" in f else h.get("hint"), "fill": h.get("fill")}, h["no"])
            h.clear()
            h.update(new)
        else:
            h = _heading({"name": f["name"], "hint": f.get("hint")}, max(h["no"] for h in s["headings"]) + 1)
            s["headings"].append(h)
        _save(area, data)
    return h


def meetings(area: dict, s: dict) -> list[tuple[int, Path]]:
    """The series' meetings as (number, folder), in order. A folder is named from the project's folder."""
    root = areas.transcripts(area)
    return sorted((x["no"], root / x["dir"] if not Path(x["dir"]).expanduser().is_absolute() else Path(x["dir"]).expanduser())
                  for x in s["meetings"])


def next_no(s: dict) -> int:
    return max((x["no"] for x in s["meetings"]), default=0) + 1


def file(area: dict, sid: str, d: Path, no: int | None = None) -> int:
    """The meeting in `d` is the series' meeting `no`, the next without one. A meeting already filed keeps its number.
    Under the knowledge base's lock."""
    data = load(area)
    s = get(data, sid)
    d, root = Path(d).expanduser().resolve(), areas.transcripts(area).resolve()
    name = d.name if d.parent == root else knowledge.tilde(d)
    have = next((x for x in s["meetings"] if x["dir"] == name), None)
    if have and no in (None, have["no"]):
        return have["no"]
    no = next_no(s) if no is None else no
    if no < 1:
        raise ArgError(f"bad meeting number: {no}")
    if any(x["no"] == no and x["dir"] != name for x in s["meetings"]):
        raise ArgError(f"{s['name']} {no} is another meeting")
    if have:
        have["no"] = no
    else:
        s["meetings"].append({"no": no, "dir": name})
    _save(area, data)
    return no


def filed(area: dict, s: dict, d: Path) -> int | None:
    """The number the meeting in `d` has in the series, None when it is not filed."""
    d = Path(d).expanduser().resolve()
    return next((no for no, x in meetings(area, s) if x.resolve() == d), None)


def agenda(area_id: str, sid: str) -> dict:
    """The next meeting's agenda: its number, the headings, and under each the points earlier meetings left open."""
    from . import protocol
    area = areas.get_known(areas.load(), area_id)
    s = get(load(area), sid)
    no = next_no(s)
    still = protocol.open_points(area, s, no)
    return {"series": s["id"], "name": s["name"], "no": no,
            "headings": [h | {"open": [p for p in still if p["heading"] == h["no"]]} for h in s["headings"]]}
