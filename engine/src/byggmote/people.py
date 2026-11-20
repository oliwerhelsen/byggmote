"""people.json in Byggmöte's folder: the global person list. Written by the app and by the people commands here."""
import re
import unicodedata

from . import ArgError, areas, read_json


class InUse(ValueError):
    """Delete refused: meetings link the person."""
    def __init__(self, msg: str, meetings: list[str]):
        super().__init__(msg)
        self.meetings = meetings


def path():
    return areas.path().with_name("people.json")


def slug(name: str, empty: str = "person") -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or empty


def load() -> list[dict]:
    areas.load()  # creates people.json if missing
    return read_json(path(), "people")["people"]


def save(ps: list[dict]):
    areas._write(path(), {"people": ps})


def resolve(ref: str, cfg: dict, area_id: str, ps: list[dict]) -> dict | None:
    """`@id` must exist. Text links if exactly one person has it as name or short, area members first."""
    if ref.startswith("@"):
        hit = next((p for p in ps if p["id"] == ref[1:]), None)
        if not hit:
            raise ArgError(f"unknown person: {ref}")
        return hit
    members = area_members(cfg, area_id, ps)
    for group in ([p for p in ps if p["id"] in members], ps):
        hit = [p for p in group if ref in (p["name"], p.get("short"))]
        if hit:
            return hit[0] if len(hit) == 1 else None
    return None


def in_all_areas(cfg: dict, ps: list[dict]) -> set:
    """Me and people with `all_areas`: members of every area."""
    return {cfg.get("me")} | {p["id"] for p in ps if p.get("all_areas")}


def area_members(cfg: dict, area_id: str, ps: list[dict]) -> set:
    """The area's people, me and people with `all_areas`."""
    area = next((a for a in cfg["areas"] if a["id"] == area_id), {})
    return in_all_areas(cfg, ps) | {x["person"] for x in area.get("people", [])}


def new(name: str, ps: list[dict]) -> dict:
    """A person from a full name: an id from it (`-2`, `-3`… when taken), short = the first word when it has several."""
    base, n, taken = slug(name), 2, {x["id"] for x in ps}
    pid = base
    while pid in taken:
        pid, n = f"{base}-{n}", n + 1
    return {"id": pid, "name": name} | ({"short": name.split()[0]} if " " in name else {})


def label(p: dict) -> str:
    return p.get("short") or p["name"]


def _get(ps: list[dict], pid: str) -> dict:
    hit = next((p for p in ps if p["id"] == pid.removeprefix("@")), None)
    if not hit:
        raise ValueError(f"unknown person: {pid}")
    return hit


def _leave_areas(cfg: dict, pid: str):
    for a in cfg["areas"]:
        a["people"] = [x for x in a.get("people", []) if x["person"] != pid]


def set_me(ref: str) -> dict:
    """`@id`, or a full name: that person, else a new one (short = first word). Me belongs to every area implicitly."""
    cfg, ps = areas.load(), load()
    ref = " ".join(ref.split())
    if not ref.removeprefix("@"):
        raise ArgError("expected a name or @id")
    if ref.startswith("@") and not any(p["id"] == ref[1:] for p in ps):
        raise ArgError(f"unknown person: {ref}")  # a bad argument, exit 2 (SPEC, General)
    p = _get(ps, ref) if ref.startswith("@") else next((p for p in ps if p["name"] == ref), None)
    if not p:
        p = new(ref, ps)
        save(ps + [p])
    cfg["me"] = p["id"]
    _leave_areas(cfg, p["id"])
    areas.save(cfg)
    return p


def merge(removed: str, kept: str) -> list[str]:
    """`removed` becomes `kept` in every meeting, area, role, voice match and Sounds like, then disappears. Returns the rewritten
    meetings. Meetings first: if one fails, `removed` still exists and the merge can be run again."""
    from . import knowledge, meeting
    from .learn import _split
    with knowledge.locked(knowledge.folder()):
        cfg, ps = areas.load(), load()
        r, k = _get(ps, removed), _get(ps, kept)
        if r["id"] == k["id"]:
            raise ArgError("cannot merge a person into itself")
        if r["id"] == cfg.get("me"):
            raise ValueError("cannot merge away me; merge the other person into me")
        done = []
        for d, m in meeting.everywhere(cfg):
            matched = [s for s in m["speakers"] if (s.get("voice") or {}).get("person") == r["id"]]
            if not meeting.links(m, r["id"]) and not matched:
                continue
            # Kept's own speakers too: their name may be the long form because the short one was taken by `removed`. Removed's are
            # kept's first, so the short one is free whichever speaker comes first.
            for s in m["speakers"]:
                if s.get("person") == r["id"]:
                    s["person"] = k["id"]
            meeting.rename(m, [f"{s['id']}=@{k['id']}" for s in m["speakers"] if s.get("person") == k["id"]])
            for t in m.get("tracks", []):
                if t.get("person") == r["id"]:
                    t["person"] = k["id"]
            for s in matched:
                s["voice"]["person"] = k["id"]
            meeting.save(d, m, transcript=False)
            done.append(d)
        for a in cfg["areas"]:
            ap = a.get("people", [])
            i = next((i for i, x in enumerate(ap) if x["person"] == r["id"]), None)
            if i is None:
                continue
            role = ap.pop(i).get("role")
            mine = next((x for x in ap if x["person"] == k["id"]), None)
            if mine and not mine.get("role") and role:
                mine["role"] = role
            elif not mine and k["id"] != cfg.get("me"):
                ap.insert(i, {"person": k["id"]} | ({"role": role} if role else {}))
        for f in ("short", "email"):
            if not k.get(f) and r.get(f):
                k[f] = r[f]
        if r.get("note") and r["note"] != k.get("note"):
            k["note"] = "; ".join(filter(None, (k.get("note"), r["note"])))
        if r.get("all_areas") and k["id"] != cfg.get("me"):
            k["all_areas"] = True
        others = [p for p in ps if p["id"] != r["id"]]
        heard = [h for x in (cfg, *cfg["areas"]) for e in x.get("vocabulary", []) for t, hs in [_split(e)]
                 if _named(r, t) and not any(_named(o, t) for o in others) for h in hs]
        sounds_like(cfg, ps, r, [], r)  # removed's lines go
        sounds_like(cfg, others, k, heard)  # their forms on kept's
        areas.save(cfg)  # before people.json: nothing may point at a deleted person
        save(others)
        for d in done:
            meeting.write_transcript(d, meeting.load(d))  # moved role and note
    return [str(d) for d in done]


def delete(pid: str, force: bool = False) -> list[str]:
    """Refuses while meetings link the person (InUse lists them). `force` unlinks them first; speakers keep their name."""
    from . import meeting
    cfg, ps = areas.load(), load()
    p = _get(ps, pid)
    if p["id"] == cfg.get("me"):
        raise ValueError("cannot delete me")
    linked = [(d, m) for d, m in meeting.everywhere(cfg) if meeting.links(m, p["id"])]
    if linked and not force:
        n = len(linked)
        raise InUse(f"{n} meeting{'s link' if n != 1 else ' links'} {p['id']}", [str(d) for d, _ in linked])
    for d, m in linked:
        for x in m["speakers"] + m.get("tracks", []):
            if x.get("person") == p["id"]:
                x["person"] = None
        meeting.save(d, m)
    _leave_areas(cfg, p["id"])
    areas.save(cfg)
    save([x for x in ps if x["id"] != p["id"]])
    return [str(d) for d, _ in linked]


# Editing people (docs/SPEC.md, Editing the knowledge base; #796): the apps write people.json through these, under the knowledge base's lock.

FIELDS = {"name": str, "short": (str, type(None)), "note": (str, type(None)), "email": (str, type(None)), "all_areas": bool,
          "areas": list, "heard": list}


def _named(p: dict, term: str) -> bool:
    from .learn import key
    return key(term) in {key(n) for n in (p.get("name"), p.get("short")) if n}


def _text(p: dict, f: dict, k: str):
    """An optional field: set when given with text, removed when given empty or null."""
    if k not in f:
        return
    if (f[k] or "").strip():
        p[k] = f[k].strip()
    else:
        p.pop(k, None)


def _heard(f: dict) -> list[str] | None:
    from .learn import _forms
    if "heard" not in f:
        return None
    if not all(isinstance(h, str) for h in f["heard"]):
        raise ArgError("heard: expected a list of text")
    return [x for h in f["heard"] for x in _forms(h)]


def _memberships(cfg: dict, f: dict) -> dict[str, str | None] | None:
    """`areas` checked: area id to role, in order."""
    if "areas" not in f:
        return None
    out = {}
    for x in f["areas"]:
        if not isinstance(x, dict) or not isinstance(x.get("area"), str) or not isinstance(x.get("role") or "", str) \
                or set(x) - {"area", "role"}:
            raise ArgError("areas: expected [{\"area\": ID, \"role\": TEXT}]")
        areas.get_known(cfg, x["area"])
        out.setdefault(x["area"], (x.get("role") or "").strip() or None)
    return out


def _join(cfg: dict, p: dict, member: dict[str, str | None]):
    """The person in exactly these areas with these roles; a place in an area's list is kept."""
    for a in cfg["areas"]:
        ap = a.setdefault("people", [])
        i = next((i for i, x in enumerate(ap) if x["person"] == p["id"]), None)
        if a["id"] not in member:
            if i is not None:
                ap.pop(i)
            continue
        entry = {"person": p["id"]} | ({"role": member[a["id"]]} if member[a["id"]] else {})
        if i is None:
            ap.append(entry)
        else:
            ap[i] = entry


def _unique(forms: list[str]) -> list[str]:
    """Once each, ignoring case, the first spelling kept."""
    from .learn import key
    seen, out = set(), []
    for x in forms:
        if key(x) not in seen:
            seen.add(key(x))
            out.append(x)
    return out


def sounds_like(cfg: dict, ps: list[dict], p: dict, heard: list[str] | None, old: dict | None = None):
    """Sounds like as Byggmöte's People saves it (#513): `p` as it is now, `old` as it was (None when new, which only adds; `heard` None
    keeps the forms, so a new name still respells the lines).
    A line is the person's when its term is their name or short name (or was) and nobody else's. Each line keeps the forms still
    wanted, where it is, with the person's spelling; new forms go on the first (a root line when there is none); a line left without
    forms goes. Other lines stay as they are written."""
    from .learn import _entry, _set, _split, key
    holders = [cfg, *cfg["areas"]]
    rows = [{"in": h, "line": e, "term": _split(e)[0], "heard": _split(e)[1]} for h in holders for e in h.get("vocabulary", [])]
    others = [x for x in ps if x["id"] != p["id"]]
    mine = [r for r in rows if (_named(p, r["term"]) or (old and _named(old, r["term"])))
            and not any(_named(o, r["term"]) for o in others)]
    had = _unique([h for r in mine for h in r["heard"]])
    want = _unique((had if old is None or heard is None else []) + (heard or []))
    if [key(x) for x in want] == [key(x) for x in had] and all(_named(p, r["term"]) for r in mine):
        return
    left = {key(x) for x in want}
    for r in mine:
        kept = []
        for h in r["heard"]:
            if key(h) in left:
                left.remove(key(h))
                kept.append(h)
        r["heard"], r["line"] = kept, None
        if not _named(p, r["term"]):
            r["term"] = label(p)
    added = [x for x in want if key(x) in left]
    if added:
        if mine:
            mine[0]["heard"] += added
        else:
            rows.append({"in": cfg, "line": None, "term": label(p), "heard": added})
    for h in holders:
        _set(h, [r["line"] or _entry(r["term"], r["heard"]) for r in rows if r["in"] is h and (r["line"] or r["heard"])])


def add(given) -> dict:
    """A new person; a name already in people.json is that person, unchanged (as Byggmöte's New Person)."""
    from . import knowledge
    f = areas.fields(given, FIELDS, ("name",))
    heard = _heard(f)
    with knowledge.locked(knowledge.folder()):
        cfg, ps = areas.load(), load()
        member = _memberships(cfg, f)
        name = " ".join(f["name"].split())
        if hit := next((p for p in ps if p["name"] == name), None):
            return hit
        p = new(name, ps)
        for k in ("short", "note", "email"):
            if (f.get(k) or "").strip():
                p[k] = f[k].strip()
        if f.get("all_areas"):
            p["all_areas"] = True
        ps.append(p)
        if member and not p.get("all_areas"):
            _join(cfg, p, member)
        if heard:
            sounds_like(cfg, ps, p, heard)
        save(ps)  # before areas.json: nothing may point at a person not there
        areas.save(cfg)
    return p


def set_person(pid: str, given) -> dict:
    from . import knowledge
    f = areas.fields(given, FIELDS)
    if "name" in f and not f["name"].strip():
        raise ArgError("missing name")
    heard = _heard(f)
    with knowledge.locked(knowledge.folder()):
        cfg, ps = areas.load(), load()
        p = next((x for x in ps if x["id"] == pid), None)
        if not p:
            raise ArgError(f"unknown person: {pid}")
        if p["id"] == cfg.get("me") and ("all_areas" in f or "areas" in f):
            raise ArgError("me is in every area")
        member = _memberships(cfg, f)
        old = dict(p)
        if "name" in f:
            p["name"] = " ".join(f["name"].split())
        for k in ("short", "note", "email"):
            _text(p, f, k)
        if "all_areas" in f:
            if f["all_areas"]:
                p["all_areas"] = True
            else:
                p.pop("all_areas", None)
        if member is not None and not p.get("all_areas"):
            _join(cfg, p, member)
        sounds_like(cfg, ps, p, heard, old)
        save(ps)  # before areas.json: nothing may point at a person not there
        areas.save(cfg)
    return p

