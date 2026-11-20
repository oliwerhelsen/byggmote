"""What Byggmöte learns by itself from a meeting (#818): terms, spellings and heard forms into areas.json, a known person into
the meeting's area, recorded in learning.json with exactly what changed, so undo takes back that and nothing else
(docs/SPEC.md, `byggmote learn`). New people and voices stay proposals, because a mistake there spreads; with
`everything` (Byggmöte's `--all`, #898) they apply too, with the same undo."""
import json
import re
from pathlib import Path

from . import areas, atomic_write, context, knowledge, meeting, people, read_json


def path() -> Path:
    return knowledge.folder() / "learning.json"


def load() -> dict:
    """Missing: nothing learned. One Byggmöte can't read stops here, before anything is written."""
    p = path()
    d = read_json(p) if p.exists() else {}
    d.setdefault("schema", 1)
    if not isinstance(d.setdefault("meetings", {}), dict) or not isinstance(d.setdefault("skipped", []), list):
        raise ValueError(f"cannot read {p}: expected meetings and skipped")
    return d


def save(d: dict):
    atomic_write(path(), json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def meeting_key(d: Path, m: dict) -> str:
    """As the app keys a meeting (`Library.learnedKey`): it stays when the meeting moves."""
    return m.get("created_at") or d.name


def key(s: str) -> str:
    """A term or heard form as the app compares them (`Term.key`)."""
    return s.strip().lower()


def title(p: dict) -> str:
    t = p.get("term") if p.get("kind") == "term" else p.get("name")
    return t if isinstance(t, str) else ""  # a proposal's title that is not text is none


def pid(p: dict) -> str:
    """The proposal's key, as `skipped` has it. A voice is one speaker in one meeting, as `merge` keys it."""
    k = p.get("kind")
    s = f"{(p.get('sources') or [''])[0]}:{p.get('speaker')}" if k == "voice" else title(p)
    return f"{k}:{(s or '').lower()}"


def _forms(heard: str) -> list[str]:
    return [h.strip() for h in re.split(r"[,/]", heard or "") if h.strip()]


def _split(entry: str) -> tuple[str, list[str]]:
    t, _, h = entry.partition("=")
    return t.strip(), _forms(h)


def junk(s: str) -> bool:
    """A time or a file name is no term (#1268): "12 56", "MOM-2026-10-19-veckomote"."""
    return not re.search(r"[^\W\d_]", s) or re.search(r"\d{4}-\d\d-\d\d", s) is not None


def risky(form: str) -> bool:
    """A heard form replaces those words everywhere (`context.Vocab.replace`): a common word or a short one would rewrite
    every transcript and dictation, so the user says yes to it."""
    ws = [context.key(w) for w in form.split()]
    return junk(form) or len("".join(ws)) < 4 or any(w in context.SV | context.EN for w in ws)


def _near(form: str, known: set[str]) -> bool:
    """`form` is, or is one letter off, a known name or term: as a heard form it would rewrite that one too, since
    `context.Vocab.replace` also takes words one letter off (#1268: Martus made Markus Marcus Andersson)."""
    k = context.key(form)
    return any(k == x or context.one_off(x, k) for x in known)


def _entry(t: str, forms: list[str]) -> str:
    return f"{t} = {', '.join(forms)}" if forms else t


def _holder(cfg: dict, area: str | None) -> dict | None:
    """Where the area's lines are: the root for Everywhere; None for an area that is gone."""
    return cfg if area is None else next((a for a in cfg["areas"] if a["id"] == area), None)


def _line(lines: list[str], t: str) -> int | None:
    return next((i for i, e in enumerate(lines) if key(_split(e)[0]) == key(t)), None)


def _set(holder: dict, lines: list[str]):
    if lines:
        holder["vocabulary"] = lines
    else:
        holder.pop("vocabulary", None)


def join(cfg: dict, who: dict, a: str | None, role: str | None = None) -> dict:
    """The person into area `a`, as a known person joins it; what changed."""
    if not a or who["id"] == cfg.get("me") or who.get("all_areas"):
        return {}
    members = _holder(cfg, a).setdefault("people", [])
    if any(x.get("person") == who["id"] for x in members):
        return {}
    entry = {"person": who["id"]} | ({"role": role} if role else {})
    members.append(entry)
    return {"joined": entry | {"area": a}}


def _apply(cfg: dict, ps: list[dict], p: dict, everything: bool = False) -> dict:
    """`p` into `cfg` (and `ps`), as Add does it (SPEC, Proposals); what changed, empty when nothing did or it must ask."""
    if not isinstance(p.get("heard"), (str, type(None))):
        return {}
    t, a = title(p).strip(), p.get("area")
    seen: set[str] = set()
    heard = [h for h in _forms(p.get("heard")) if key(h) not in seen and not seen.add(key(h))]  # each form once
    who = next((x for x in ps if x["name"] == t), None)
    fresh = p.get("kind") == "person" and not who
    # A title with = would be a replacement rule, not a term (as `terms add` refuses it).
    if not t or "=" in t or junk(t) or p.get("kind") not in ("term", "person") or any(map(risky, heard)):
        return {}
    if fresh and (not everything or " " not in t):
        return {}  # one word is no new person: Janne, Ola (#1268)
    said = t
    if (who or fresh) and heard and not any(" " in h for h in heard):
        said = (who or p).get("short") or t.split()[0]  # a first name heard wrong: "Clas" was said, not "Klas Eskilsson" (#1268)
    known = context.Vocab(context.entries(cfg, ps)).known - {context.key(said)} if heard else set()
    if any(_near(h, known) for h in heard):
        return {}
    changed = {}
    if fresh:
        who = people.new(t, ps) | {k: p[k] for k in ("short", "note") if isinstance(p.get(k), str) and p[k].strip()}
        if a is None:
            who["all_areas"] = True
        ps.append(who)
        changed["created"] = who["id"]
        changed |= join(cfg, who, a, p.get("role") if isinstance(p.get("role"), str) else None)
    elif who:
        changed |= join(cfg, who, a)
    if who and not heard:  # a person's name needs no line: dictation has it
        return changed
    everywhere = _line(cfg.get("vocabulary") or [], said) is not None
    if not heard and everywhere:  # Everywhere has it already
        return changed
    # New heard forms for a term on the Everywhere line go there, so one line keeps them (#767).
    where = None if heard and everywhere else a
    holder = _holder(cfg, where)
    lines = list(holder.get("vocabulary") or [])
    i = _line(lines, said)
    if i is None:
        lines.append(_entry(said, heard))
        changed["vocabulary"] = {"area": where, "term": said, "new": True, "heard": heard}
    else:
        spelled, have = _split(lines[i])
        seen = {key(x) for x in have}
        new = [h for h in heard if key(h) not in seen and not seen.add(key(h))]
        if new:
            lines[i] = _entry(spelled, have + new)
            changed["vocabulary"] = {"area": where, "term": spelled, "new": False, "heard": new}
    _set(holder, lines)
    return changed


def _taught(changed: dict) -> list[str]:
    who = changed.get("created") or (changed.get("voice") or {}).get("person") or (changed.get("joined") or {}).get("person")
    return ([f"person:{who}"] if who else []) + ([f"term:{changed['vocabulary']['term'].lower()}"] if "vocabulary" in changed else [])


AUTO = re.compile(re.escape(meeting.UNNAMED) + r"\d+")


def _voices(d: Path, m: dict, cfg: dict, ps: list[dict], seen: set) -> list[dict]:
    """The meeting's voice matches (`speakers[].voice`, SPEC `run`) linked as `rename @ID` does: only an automatic speaker, and a
    person linked to no other speaker, since that would be a merge. The applied entries."""
    applied = []
    for s in m["speakers"]:
        who = next((x for x in ps if x["id"] == (s.get("voice") or {}).get("person")), None)
        if s.get("person") or not AUTO.fullmatch(s.get("name") or "") or not who or meeting.links(m, who["id"]):
            continue
        p = {"kind": "voice", "speaker": s["id"], "person": who["id"], "name": who["name"], "area": m["area"], "reason": "", "sources": [d.name]}
        if (key := pid(p)) in seen:
            continue
        before = s["name"]
        meeting.rename(m, [f"{s['id']}=@{who['id']}"])
        seen.add(key)
        applied.append(p | {"changed": {"voice": {"speaker": s["id"], "person": who["id"], "name": before}} | join(cfg, who, m["area"])})
    return applied


def apply(d: Path, proposals: list[dict], everything: bool = False) -> dict:
    """The meeting's proposals: the ones Byggmöte learns by itself applied and recorded, the rest returned. `everything`: also a new
    person and the meeting's voice matches (Byggmöte, #898)."""
    with knowledge.locked(knowledge.folder()):  # meetings finishing at once: each reads and writes both files
        return _apply_all(d, proposals, everything)


def _apply_all(d: Path, proposals: list[dict], everything: bool) -> dict:
    m, cfg, ps, ln = meeting.load(d), areas.load(), people.load(), load()
    if m.get("area", areas.DEFAULT) == areas.DEFAULT:
        return {"applied": [], "proposals": proposals}
    rec = ln["meetings"].get(meeting_key(d, m)) or {}
    ids = {a["id"] for a in cfg["areas"]}
    seen = set(ln["skipped"]) | {pid(x) for x in rec.get("applied") or []}
    applied, rest, n = [], [], len(ps)
    for p in proposals:
        ok = isinstance(p, dict) and pid(p) not in seen and (p.get("area") is None or p.get("area") in ids)
        changed = _apply(cfg, ps, p, everything) if ok else {}
        if changed:
            seen.add(pid(p))
            applied.append(p | {"changed": changed})
        else:
            rest.append(p)
    voices = _voices(d, m, cfg, ps, seen) if everything else []
    applied += voices
    if applied:
        if len(ps) > n:
            people.save(ps)  # before areas.json: nothing may point at a person who is not there
        areas.save(cfg)  # only now: a run that applies nothing leaves the file as it is
        if voices:
            meeting.save(d, m)
        rec = ln["meetings"].setdefault(meeting_key(d, m), {})
        rec["applied"] = (rec.get("applied") or []) + applied
        learned = rec.get("learned") or []
        rec["learned"] = learned + [x for x in dict.fromkeys(y for p in applied for y in _taught(p["changed"])) if x not in learned]
        save(ln)
    return {"applied": applied, "proposals": rest}


def _guess(p: dict, ps: list[dict]) -> dict:
    """What an entry the app applied before #818 changed (#487): a person's name joined the area, else a line without heard forms."""
    t, a = title(p), p.get("area")
    who = next((x for x in ps if x["name"] == t), None)
    if who:
        return {"joined": {"person": who["id"], "area": a}} if a else {}
    return {"vocabulary": {"area": a, "term": t, "new": True, "heard": []}}


def _used(person: str, d: Path, m: dict, cfg: dict) -> bool:
    """A person a meeting links, or an area has."""
    return any(x.get("person") == person for a in cfg["areas"] for x in a.get("people") or []) or meeting.links(m, person) or \
        any(meeting.links(o, person) for od, o in meeting.everywhere(cfg) if od.resolve() != d.resolve())


def undo(d: Path, k: str) -> bool:
    """Takes back what the meeting applied under `k`, as far as it is still there and no other meeting learned it."""
    with knowledge.locked(knowledge.folder()):
        return _undo(d, k)


def _undo(d: Path, k: str) -> bool:
    m, cfg, ps, ln = meeting.load(d), areas.load(), people.load(), load()
    mk = meeting_key(d, m)
    rec = ln["meetings"].get(mk) or {}
    entry = next((x for x in rec.get("applied") or [] if pid(x) == k), None)
    if entry is None:
        return False
    changed = entry.get("changed") or _guess(entry, ps)
    others = [r for x, r in ln["meetings"].items() if x != mk and isinstance(r, dict)]

    def claimed(t: str, area: str | None = ...) -> bool:
        """Another meeting learned `t` too; with `area`, only in that area: the same term or person in another area is its own
        line or place, which this undo does not touch. A meeting's `learned` without its applied entry (older) counts everywhere."""
        for r in others:
            if t not in (r.get("learned") or []):
                continue
            mine = [x for x in r.get("applied") or [] if t in _taught(x.get("changed") or {})]
            if area is ... or not mine:
                return True
            for x in mine:
                c = x["changed"]
                if t.startswith("term:") and c.get("vocabulary", {}).get("area") == area:
                    return True
                if t.startswith("person:") and (c.get("joined") or {}).get("area", area) == area:
                    return True
        return False
    taught, before = _taught(changed), json.dumps(cfg)
    if (j := changed.get("joined")) and not claimed(f"person:{j['person']}", j["area"]) and (h := _holder(cfg, j["area"])) is not None:
        added = {f: v for f, v in j.items() if f != "area"}
        h["people"] = [x for x in h.get("people") or [] if x != added]  # given another role since: the user's
    if (v := changed.get("vocabulary")) and (h := _holder(cfg, v["area"])) is not None:
        lines = list(h.get("vocabulary") or [])
        if (i := _line(lines, v["term"])) is not None:
            spelled, have = _split(lines[i])
            gone = {key(x) for x in v["heard"]}
            left = [x for x in have if key(x) not in gone]
            if v["new"] and not left and not claimed(f"term:{v['term'].lower()}", v["area"]):
                del lines[i]
            else:
                lines[i] = _entry(spelled, left)
            _set(h, lines)
    if (v := changed.get("voice")) and (s := next((x for x in m["speakers"] if x["id"] == v["speaker"]), None)) and s.get("person") == v["person"]:
        s["name"], s["person"] = v["name"], None  # named since: the user's
        meeting.save(d, m)
    if json.dumps(cfg) != before:
        areas.save(cfg)
    if (c := changed.get("created")) and not claimed(f"person:{c}") and c != cfg.get("me") and not _used(c, d, m, cfg):
        people.save([x for x in ps if x["id"] != c])  # after areas.json, which no longer points at them
    rec["applied"] = [x for x in rec["applied"] if x is not entry]
    rec["learned"] = [x for x in rec.get("learned") or [] if x not in taught]
    ln["skipped"] = sorted(set(ln["skipped"]) | {k})
    save(ln)
    return True


def correct(d: Path, k: str, spelling: str) -> bool:
    """Respells the term or person the meeting applied under `k` (#1040); undo still takes it back afterwards."""
    with knowledge.locked(knowledge.folder()):
        return _correct(d, k, " ".join(spelling.split()))


def _respell(cfg: dict, v: dict, new: str) -> str | None:
    """The line `v` names (`changed` `vocabulary`) spelled `new`, with the old spelling as a heard form; that form, or None."""
    h = _holder(cfg, v["area"])
    lines = list((h or {}).get("vocabulary") or [])
    i = _line(lines, v["term"])
    if i is None:
        return None
    if (j := _line(lines, new)) is not None and j != i:
        raise ValueError(f"{_split(lines[j])[0]} is already a term there")
    old, have = _split(lines[i])
    form = old if key(old) != key(new) and not risky(old) and key(old) not in {key(x) for x in have} else None
    lines[i] = _entry(new, have + ([form] if form else []))
    _set(h, lines)
    return form


def _correct(d: Path, k: str, new: str) -> bool:
    m, cfg, ps, ln = meeting.load(d), areas.load(), people.load(), load()
    entry = next((x for x in (ln["meetings"].get(meeting_key(d, m)) or {}).get("applied") or [] if pid(x) == k), None)
    if entry is None or entry.get("kind") not in ("term", "person"):
        return False
    changed = entry.setdefault("changed", _guess(entry, ps))
    who_id = changed.get("created") or (changed.get("joined") or {}).get("person")
    who = next((x for x in ps if x["id"] == who_id), None)
    if who_id and not who:
        return False
    if who and not changed.get("created"):  # #1073: one meeting renames only a person it created
        raise ValueError(f"{who['name']} was in People before this meeting: change the name in People")
    if who and (taken := next((x for x in ps if x is not who and key(x["name"]) == key(new)), None)):
        raise ValueError(f"{taken['name']} is already a person")
    old = title(entry)
    v = changed.get("vocabulary")
    if v and _line(list((_holder(cfg, v["area"]) or {}).get("vocabulary") or []), v["term"]) is None:
        v = None  # the user removed the line since: nothing of it to respell
    if not who and not v:
        return False
    was, to = (v["term"] if v else old), new
    if who and v and key(was) != key(old):  # the line is on the short name (#1268): it follows a short Byggmöte gave
        first = who["name"].split()[0]
        to = (new.split()[0] if " " in new else new) if who.get("short", first) == first else was
    if v and (form := _respell(cfg, v, to)) and v.get("new"):
        v["heard"] = v["heard"] + [form]  # undo removes it with the rest, so the new line goes
    area = v["area"] if v else entry.get("area")
    for r in ln["meetings"].values():
        if not isinstance(r, dict):
            continue
        line = False  # the meeting learned this line: its `learned` follows the new spelling
        for x in r.get("applied") or []:
            xc = x.get("changed") or {}
            xv = xc.get("vocabulary")
            if v and xv and xv["area"] == v["area"] and key(xv["term"]) == key(was):
                xv["term"], line = to, True
            # Only the same thing: a term in the same area (another area's is its own line), the same person.
            same = (xc.get("created") or (xc.get("joined") or {}).get("person")) == who["id"] if who and xc else \
                (xv or {}).get("area", x.get("area")) == area
            if x.get("kind") == entry["kind"] and key(title(x)) == key(old) and same:
                x["term" if x["kind"] == "term" else "name"] = new
            if who and x.get("kind") == "voice" and x.get("person") == who["id"]:
                x["name"] = new
        if line:
            r["learned"] = list(dict.fromkeys(f"term:{to.lower()}" if t == f"term:{was.lower()}" else t for t in r.get("learned") or []))
    if who:
        first = who["name"].split()[0]
        who["name"] = new
        if who.get("short", first) == first:  # the short form Byggmöte gave, not one the user chose
            who.pop("short", None)
            who.update({"short": new.split()[0]} if " " in new else {})
        people.save(ps)  # before the speakers: `rename @ID` reads the name from people.json
    areas.save(cfg)
    save(ln)
    if who:  # last: a speaker's name only shows the person's, so one not renamed leaves nothing that disagrees
        found = dict(meeting.everywhere(cfg))
        for md, mm in [(d, m)] + [(x, y) for x, y in found.items() if x.resolve() != d.resolve()]:
            if meeting.links(mm, who["id"]):
                meeting.rename(mm, [f"{s['id']}=@{who['id']}" for s in mm["speakers"] if s.get("person") == who["id"]])
                meeting.save(md, mm)
    return True
