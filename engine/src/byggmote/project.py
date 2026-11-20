"""A server project's knowledge (docs/SPEC.md, `byggmote project`; decision 29): what a meeting taught goes to the
server with the meeting, and the server's people and terms come back into the project's area. The server wins for its project; a local
project, the root vocabulary and voice prints are never touched here."""
import json
from pathlib import Path

from . import ArgError, areas, atomic_write, knowledge, learn, meeting, people


def path() -> Path:
    """The last knowledge each server project's sync applied, by the customer's short name: it holds the server's term ids, which the
    vocabulary's lines cannot, so a later fetch can follow a correction or a removal."""
    return areas.path().with_name("server.json")


def _copies() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _area(cfg: dict, aid: str) -> dict:
    a = areas.get_known(cfg, aid)
    if not a.get("server"):
        raise ArgError(f"{aid} is not a server project")
    return a


def taught(d: Path) -> dict:
    """What the meeting taught in its server project, as the server takes it: the people it created or that joined the project, with
    their role there, and the project's terms it added or gave heard forms. Never a voice print, never Everywhere's lines."""
    m = meeting.load(d)
    cfg = areas.load()
    a = _area(cfg, m["area"])
    ps = {p["id"]: p for p in people.load()}
    rec = learn.load().get("meetings", {}).get(learn.meeting_key(d, m), {})
    roles = {x["person"]: x.get("role") for x in a.get("people", [])}
    lines = {learn.key(learn._split(e)[0]): learn._split(e) for e in a.get("vocabulary") or []}
    who, terms = [], []
    for k in rec.get("learned") or []:
        kind, _, v = k.partition(":")
        if kind == "person" and v in ps and v != cfg.get("me") and v not in who:
            who.append(v)
        elif kind == "term" and v in lines and v not in terms:
            terms.append(v)
    out_people = []
    for pid in who:
        p = ps[pid]
        out_people.append({"name": p["name"]} | ({"short": p["short"]} if p.get("short") else {})
                          | ({"role": roles[pid]} if roles.get(pid) else {}))
    return {"people": out_people, "terms": [{"spelling": lines[t][0], "heardAs": lines[t][1]} for t in terms]}


def _person(ps: list[dict], short: str, pid: str) -> dict | None:
    return next((p for p in ps if (p.get("server") or {}).get(short) == pid), None)


def _unlink(cfg: dict, a: dict, p: dict, short: str):
    """The person leaves this project only: elsewhere they stay who they are."""
    a["people"] = [x for x in a.get("people", []) if x["person"] != p["id"]]
    link = {k: v for k, v in (p.get("server") or {}).items() if k != short}
    if link:
        p["server"] = link
    else:
        p.pop("server", None)


# The word for a person whose name the server replaced (decision 25), in the meeting's language, as the server shows it.
FORMER = {"sv": "Tidigare medlem", "en": "Former member"}


def _remove(cfg: dict, ps: list[dict], aid: str, pid: str, replaced: bool, name: str | None = None) -> list[str]:
    """Removal reaches the app (#142): in this project's meetings only, the person's speakers are unlinked and their voice prints and voice
    matches go; with `replaced` their name becomes FORMER too, and the person goes from people.json when nothing else uses them, so the
    name is not kept here either. A meeting of another project is not touched. Returns the rewritten meetings. `name`: the name an earlier
    plain removal left on the speakers it unlinked, replaced too."""
    done = []
    for d, m in meeting.everywhere(cfg):
        if m.get("area") != aid:
            continue
        hit = False
        for x in m["speakers"] + m.get("tracks", []):
            if x.get("person") == pid or (name and x.get("person") is None and learn.key(x.get("name") or "") == learn.key(name)):
                x["person"], hit = None, True
                if x.get("embedding"):
                    x["embedding"] = None
                if replaced and "name" in x:
                    x["name"] = FORMER["en" if m.get("lang") == "en" else "sv"]
            if (x.get("voice") or {}).get("person") == pid:
                del x["voice"]
                hit = True
        if hit:
            meeting.save(d, m)
            done.append(str(d))
    p = next((q for q in ps if q["id"] == pid), None)
    used = any(pid in {x["person"] for x in a.get("people", [])} for a in cfg["areas"])         or any(meeting.links(m, pid) for _, m in meeting.everywhere(cfg))
    if replaced and p and not p.get("all_areas") and not p.get("server") and not used:
        ps.remove(p)
    return done


def sync(aid: str, given) -> dict:
    """The server's knowledge (core's KnowledgeResponse) into server project `aid`. Returns how many people and terms the project has
    from the server, and the people it took out (`removed`, with `replaced` when the server replaced the name, and the meetings rewritten).
    A removal is followed once: the person's link to the project goes with it, so the same removal seen again finds nobody."""
    if not isinstance(given, dict) or not all(isinstance(given.get(k), list) for k in ("people", "terms", "removed")):
        raise ArgError("expected the server's knowledge on stdin: {\"people\", \"terms\", \"removed\"}")
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        a = _area(cfg, aid)
        short = a["server"]
        ps = people.load()
        copies = _copies()
        before = copies.get(short) if isinstance(copies.get(short), dict) else {}
        old_terms = {t["id"]: t for t in before.get("terms", []) if isinstance(t, dict) and isinstance(t.get("id"), str)}
        # A plain removal's server id and whom it unlinked: the customer may have the name replaced later (a team member is always
        # removed first), when the link is gone.
        unlinked = {k: v for k, v in before["unlinked"].items() if isinstance(v, dict)} if isinstance(before.get("unlinked"), dict) else {}
        lines = list(a.get("vocabulary") or [])
        removed = []

        def drop_line(spelling: str):
            i = learn._line(lines, spelling)
            if i is not None:
                lines.pop(i)

        for r in given["removed"]:
            if not isinstance(r, dict) or not isinstance(r.get("id"), str):
                continue
            if r.get("kind") == "person":
                p = _person(ps, short, r["id"])
                replaced = r.get("replaced") is True
                if p:
                    _unlink(cfg, a, p, short)
                    if not r.get("mergedInto") and p["id"] != cfg.get("me"):
                        removed.append({"person": p["id"], "replaced": replaced,
                                        "meetings": _remove(cfg, ps, aid, p["id"], replaced)})
                        if not replaced:
                            unlinked[r["id"]] = {"person": p["id"], "name": p["name"]}
                elif replaced and r["id"] in unlinked:
                    was = unlinked.pop(r["id"])
                    removed.append({"person": was["person"], "replaced": True,
                                    "meetings": _remove(cfg, ps, aid, was["person"], True, was.get("name"))})
            elif r.get("kind") == "term" and r["id"] in old_terms:
                drop_line(old_terms[r["id"]]["spelling"])

        for x in given["people"]:
            if not isinstance(x, dict) or not isinstance(x.get("id"), str) or not str(x.get("name") or "").strip():
                continue
            name = " ".join(x["name"].split())
            p = _person(ps, short, x["id"]) or next(
                (q for q in ps if learn.key(q["name"]) == learn.key(name) and short not in (q.get("server") or {})), None)
            if p is None:
                p = people.new(name, ps)
                ps.append(p)
            p["name"] = name
            if str(x.get("short") or "").strip():
                p["short"] = x["short"].strip()
            p["server"] = (p.get("server") or {}) | {short: x["id"]}
            members = a.setdefault("people", [])
            entry = next((m for m in members if m["person"] == p["id"]), None)
            if p["id"] != cfg.get("me") and entry is None:
                entry = {"person": p["id"]}
                members.append(entry)
            if entry is not None and str(x.get("role") or "").strip():
                entry["role"] = x["role"].strip()

        for t in given["terms"]:
            if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not str(t.get("spelling") or "").strip():
                continue
            spelling = t["spelling"].strip()
            heard = [h.strip() for h in t.get("heardAs") or [] if isinstance(h, str) and h.strip()]
            was = old_terms.get(t["id"])
            if was and learn.key(was["spelling"]) != learn.key(spelling):
                drop_line(was["spelling"])  # corrected in the server: its old spelling is a heard form there now
            i = learn._line(lines, spelling)
            mine = learn._split(lines[i])[1] if i is not None else []
            gone = {learn.key(h) for h in (was or {}).get("heardAs", [])} - {learn.key(h) for h in heard}
            seen = {learn.key(h) for h in heard} | {learn.key(spelling)}
            # The server's forms, then those learned here and not sent yet; a form the server took out stays out.
            forms = heard + [h for h in mine if learn.key(h) not in seen | gone and not seen.add(learn.key(h))]
            if i is None:
                lines.append(learn._entry(spelling, forms))
            else:
                lines[i] = learn._entry(spelling, forms)
        learn._set(a, lines)

        people.save(ps)
        areas.save(cfg)
        copies[short] = {"people": [x for x in given["people"] if isinstance(x, dict)],
                         "terms": [x for x in given["terms"] if isinstance(x, dict)]} | ({"unlinked": unlinked} if unlinked else {})
        atomic_write(path(), json.dumps(copies, ensure_ascii=False, indent=2) + "\n")
    knowledge.guides(cfg)
    return {"people": len(given["people"]), "terms": len(given["terms"]), "removed": removed}
