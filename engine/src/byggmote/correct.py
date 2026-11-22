"""A person's corrections to a protocol. The model proposed (protocol.py); what a person sets here is the protocol.

A point a person changes keeps what the model wrote in `proposed`, one a person writes is `added`, and one taken out
goes to the protocol's `removed`, from where it can be put back: nothing a model proposed is lost, and what is a
person's can be told from what is a model's. A point's number is its name, so it stays: a removed point leaves its
number unused, and a point that is added, or moved to another heading, takes the next number there.

A protocol a later meeting builds on is not corrected, as it is not written again, and only a draft is."""
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import ArgError, areas, atomic_write, knowledge, meeting, people, protocol, series
from .context import key

MAYBE = (str, type(None))
# What a person sets on the meeting's own point, and on one an earlier meeting left open: that point's text is the
# earlier meeting's, `follow` is what this meeting says about it.
OWN = {"text": str, "kind": str, "heading": int, "role": MAYBE, "due": MAYBE, "open": bool}
CARRIED = {"follow": MAYBE, "role": MAYBE, "due": MAYBE, "open": bool}
NEW = OWN | {"line": (int, type(None))}


@contextmanager
def _editing(d: Path, points: bool = True):
    """The meeting's protocol, to change: (protocol, meeting, project). Written, with its text, when the change went
    through. Under the knowledge base's lock."""
    d = Path(d).expanduser()
    with knowledge.locked(knowledge.folder()):
        p = protocol.load(d)
        if p is None:
            raise ArgError("the meeting has no protocol")
        if p.get("status") != "draft":
            raise ArgError("the protocol is not a draft")
        m = meeting.load(d)
        area = areas.get(areas.load(), m["area"])
        s = series.get(series.load(area), p["series"])
        if points and (k := protocol.later(area, s, p["no"])) is not None:
            raise ArgError(f"{s['name']} {k} builds on this protocol")
        yield p, m, area
        p["points"].sort(key=lambda x: (x["heading"], protocol.order(x["no"])))
        atomic_write(d / protocol.FILE, json.dumps(p, ensure_ascii=False, indent=1) + "\n")
        atomic_write(d / protocol.TEXT, protocol.render(p, m, areas.name(area)))


def _point(p: dict, no: str) -> dict:
    x = next((x for x in p["points"] if x["no"] == no), None)
    if not x:
        raise ArgError(f"no point {no}")
    return x


def _next(p: dict, heading: int) -> str:
    """The next number under a heading. A removed point keeps its own, so no two points ever had the same."""
    taken = [protocol.order(x["no"]) for x in p["points"] + p.get("removed", [])]
    return f"{p['no']}.{heading}.{max((n[2] for n in taken if n[:2] == (p['no'], heading)), default=0) + 1}"


def _fields(given, allowed: dict, p: dict, area: dict) -> dict:
    """The fields a person gave, checked: a heading the protocol has points under, a kind there is, one of the
    project's roles spelled as the project spells it, a real date. An empty role, date or follow-up is none."""
    f = dict(areas.fields(given, allowed))
    if any(isinstance(f.get(k), bool) for k in ("heading", "line")):
        raise ArgError("wrong type for heading or line")
    if "text" in f:
        f["text"] = " ".join(f["text"].split())
        if not f["text"]:
            raise ArgError("missing text")
    for k in ("follow", "role", "due"):
        if k in f:
            f[k] = " ".join((f[k] or "").split()) or None
    if "kind" in f and f["kind"] not in protocol.KINDS:
        raise ArgError(f"unknown kind: {f['kind']}")
    if "heading" in f and not any(h["no"] == f["heading"] and not h.get("fill") for h in p["headings"]):
        raise ArgError(f"no heading for points: {f['heading']}")
    if f.get("role"):
        known = {key(r): r for r in protocol.roles(area)}
        if key(f["role"]) not in known:
            raise ArgError(f"the project has no Roll {f['role']}")
        f["role"] = known[key(f["role"])]
    if f.get("due"):
        try:
            f["due"] = date.fromisoformat(f["due"]).isoformat()
        except ValueError:
            raise ArgError(f"bad date: {f['due']}") from None
    return f


def _settled(f: dict, new: dict) -> dict:
    """The meeting's own point as its kind lets it be: a decision or a note is said and done, and only what stays
    open has someone to do it and a day."""
    if new["kind"] in protocol.CLOSED:
        if f.get("open"):
            raise ArgError(f"a {new['kind']} is not left open")
        new["open"] = False
    if not new["open"]:
        new["role"] = new["due"] = None
    return new


def change(d: Path, no: str, given) -> dict:
    """What a person sets on point `no` (OWN, or CARRIED for an earlier meeting's): the point as it then is.

    An amount check stays only while its amount is in the text: an amount a person writes is the person's. A role
    check goes when the person has chosen, a Roll or none, and when the point is closed: then nobody is to do it."""
    with _editing(d) as (p, _, area):
        x = _point(p, no)
        carried = "since" in x
        allowed = CARRIED if carried else OWN
        f = _fields(given, allowed, p, area)
        was = {k: x.get(k) for k in allowed}
        new = was | f if carried else _settled(f, was | f)
        if new != was:
            if "added" not in x:
                x.setdefault("proposed", was)
            x.update(new, edited=meeting.now())
            if carried:
                x["raised"] = bool(x["follow"]) or x.get("line") is not None
            elif new["heading"] != was["heading"]:
                x["no"] = _next(p, new["heading"])
            text = x["text"] + " " + (x.get("follow") or "")
            amounts = {" ".join(a.group(0).split()) for a in protocol.AMOUNT.finditer(text)}
            x["checks"] = [c for c in x["checks"] if c["code"] != "amount" or c["value"] in amounts]
        if "role" in f or not x["open"]:
            x["checks"] = [c for c in x["checks"] if c["code"] != "role"]
        return x


def add(d: Path, given) -> dict:
    """A point a person writes, from {"heading", "kind", "text"} and, when it stays open, "open", "role" and "due".
    "line" is the transcript line where it is said, if the person points at one."""
    with _editing(d) as (p, m, area):
        f = _fields(given, NEW, p, area)
        for k in ("heading", "kind", "text"):
            if k not in f:
                raise ArgError(f"missing {k}")
        line = next((x for x in protocol.lines(m) if x["id"] == f["line"]), None) if f.get("line") is not None else None
        if f.get("line") is not None and not line:
            raise ArgError(f"no line {f['line']}")
        new = _settled(f, {k: f.get(k) for k in OWN} | {"open": bool(f.get("open"))})
        x = {"no": _next(p, f["heading"])} | new | {"at": line and line["at"], "line": line and line["id"], "quote": None,
                                                    "checks": [], "added": meeting.now()}
        p["points"].append(x)
        return x


def remove(d: Path, no: str) -> dict:
    """Point `no` out of the protocol and off the coming agendas. It is kept, to put back."""
    with _editing(d) as (p, _, _a):
        x = _point(p, no)
        if "since" in x:
            raise ArgError(f"{no} is an earlier meeting's point: it is closed, not removed")
        p["points"].remove(x)
        p.setdefault("removed", []).append(x | {"removed": meeting.now()})
        return {"removed": no}


def restore(d: Path, no: str) -> dict:
    """A removed point back in the protocol, under the number it had."""
    with _editing(d) as (p, _, _a):
        x = next((x for x in p.get("removed", []) if x["no"] == no), None)
        if not x:
            raise ArgError(f"no removed point {no}")
        p["removed"].remove(x)
        del x["removed"]
        p["points"].append(x)
        return x


def check(d: Path, no: str, n: int, undo: bool = False) -> dict:
    """A person has read check `n` (from 1) of point `no` against the recording, and the amount is right. `undo`
    takes that back. A role check is not confirmed: the person chooses a Roll, or none (`change`)."""
    with _editing(d) as (p, _, _a):
        x = _point(p, no)
        if not 1 <= n <= len(x["checks"]):
            raise ArgError(f"{no} has no check {n}")
        c = x["checks"][n - 1]
        if c["code"] != "amount":
            raise ArgError("a Roll is chosen, not confirmed")
        if undo:
            c.pop("confirmed", None)
        else:
            c["confirmed"] = meeting.now()
        return x


def _there(p: dict, m: dict, area: dict) -> list[dict]:
    """Who was there: those who spoke, then those a person added, each with the name and Roll they have now."""
    ps = people.load()
    names, role = {x["id"]: x["name"] for x in ps}, {x["person"]: x.get("role") for x in area.get("people", [])}
    spoke = protocol.attendees(m, area, ps)
    out = list(spoke)
    for a in p.get("attendees", []):
        if "added" not in a:
            continue
        if a["person"] in names:
            a = {"name": names[a["person"]]} | ({"role": role[a["person"]]} if role.get(a["person"]) else {}) | \
                {"person": a["person"], "added": a["added"]}
        if not any(x["name"] == a["name"] for x in out):
            out.append(a)
    return out


def attendees(d: Path) -> list[dict] | None:
    """Who was there, again from the meeting's speakers: for when a speaker has been named. None when the meeting has
    no draft to set them in."""
    d = Path(d).expanduser()
    if (protocol.load(d) or {}).get("status") != "draft":
        return None
    with _editing(d, points=False) as (p, m, area):
        p["attendees"] = _there(p, m, area)
        return p["attendees"]


def attend(d: Path, person: str, gone: bool = False) -> list[dict]:
    """A person of the project who was at the meeting and said nothing, or with `gone`, who was not there after all."""
    with _editing(d, points=False) as (p, m, area):
        pid = person.removeprefix("@")
        if gone:
            if not any(a.get("person") == pid and "added" in a for a in p["attendees"]):
                raise ArgError(f"{person} is not someone a person added")
            p["attendees"] = [a for a in p["attendees"] if a.get("person") != pid]
        else:
            if not any(x["person"] == pid for x in area.get("people", [])) or not any(x["id"] == pid for x in people.load()):
                raise ArgError(f"{person} is not in the project")
            p["attendees"] = _there(p | {"attendees": p["attendees"] + [{"name": pid, "person": pid, "added": meeting.now()}]}, m, area)
        return p["attendees"]
