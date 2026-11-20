"""Naming a speaker as the user does it, for both apps (#897, docs/SPEC.md `name`): a typed new name creates the person, a person
outside the meeting's area joins it, and Remove Name takes back a person the meeting brought, when nothing else links them."""
from pathlib import Path

from . import ArgError, areas, knowledge, learn, meeting, people, voice


def name(d: Path, speaker: str, new: str, email: str | None = None) -> dict:
    with knowledge.locked(knowledge.folder()):  # reads and writes people.json, areas.json and learning.json
        return _name(d, speaker, " ".join(new.split()), email)  # as people add


def remove(d: Path, speaker: str) -> dict:
    with knowledge.locked(knowledge.folder()):
        return _remove(d, speaker)


def _speakers(m: dict, speaker: str) -> list[dict]:
    hit = meeting.find(m, speaker)
    if not hit:
        raise ValueError(f"no speaker: {speaker}")
    return hit


def _name(d: Path, speaker: str, new: str, email: str | None) -> dict:
    if not new:
        raise ArgError("expected a name or @id")
    m, cfg, ps = meeting.load(d), areas.load(), people.load()
    hit = _speakers(m, speaker)
    ids = {s["id"] for s in hit}
    other = None if new.startswith("@") else next((s for s in m["speakers"] if s["id"] not in ids and s["name"] == new), None)
    if other and not other.get("person"):  # merged with a free name
        for s in hit:
            s["name"], s["person"] = new, None
        meeting.save(d, m)
        return {"name": new, "person": None, "created": False, "joined": False}
    who = next((p for p in ps if p["id"] == other["person"]), None) if other else None
    who = who or people.resolve(new, cfg, m["area"], ps)
    created = who is None
    if created:
        who = people.new(new, ps) | ({"email": email} if email else {})
        ps.append(who)
        people.save(ps)  # before areas.json: nothing may point at a person who is not there
    joined = bool(learn.join(cfg, who, m["area"]))
    if joined:
        areas.save(cfg)
    meeting.rename(m, [f"{s['id']}=@{who['id']}" for s in hit])
    if not voice.on(cfg):  # Recognise Voices off: naming keeps no voice print (#1137)
        for s in hit:
            s["embedding"] = None
    meeting.save(d, m)
    if created or joined:
        ln = learn.load()
        rec = ln["meetings"].setdefault(learn.meeting_key(d, m), {})
        if (t := f"person:{who['id']}") not in (learned := rec.setdefault("learned", [])):
            learned.append(t)
        learn.save(ln)
    return {"name": hit[0]["name"], "person": who["id"], "created": created, "joined": joined}


def _remove(d: Path, speaker: str) -> dict:
    m, cfg, ps = meeting.load(d), areas.load(), people.load()
    hit = _speakers(m, speaker)
    label = _unnamed(m, {s["id"] for s in hit})
    pid = next((s["person"] for s in hit if s.get("person")), None)
    for s in hit:
        s["name"], s["person"] = label, None
    others = [o for od, o in meeting.everywhere(cfg) if od.resolve() != Path(d).resolve() and meeting.links(o, pid)] if pid else []
    # Only a meeting in this area keeps them in it; one anywhere keeps them in people.json.
    forgotten = bool(pid) and pid != cfg.get("me") and _taught(d, m, pid) and not meeting.links(m, pid) and \
        not any(o.get("area") == m["area"] for o in others)
    if forgotten:
        area = areas.get(cfg, m["area"])
        area["people"] = [x for x in area.get("people", []) if x["person"] != pid]
        areas.save(cfg)
        who = next((p for p in ps if p["id"] == pid), {})
        if not others and not who.get("all_areas") and not any(x["person"] == pid for a in cfg["areas"] for x in a.get("people", [])):
            people.save([p for p in ps if p["id"] != pid])  # after areas.json, which no longer points at them
    meeting.save(d, m)
    return {"name": label, "person": pid, "forgotten": forgotten}


def _unnamed(m: dict, ids: set[str]) -> str:
    """The speaker's own "Talare N" (its place among the diarized ones), else the first free one."""
    taken = {s["name"] for s in m["speakers"] if s["id"] not in ids}
    own = [i for i, s in enumerate((s for s in m["speakers"] if s.get("cluster")), 1) if s["id"] in ids][:1]
    return next(n for k in own + list(range(1, len(m["speakers"]) + 2)) if (n := f"{meeting.UNNAMED}{k}") not in taken)


def _taught(d: Path, m: dict, pid: str) -> bool:
    return f"person:{pid}" in ((learn.load()["meetings"].get(learn.meeting_key(d, m)) or {}).get("learned") or [])
