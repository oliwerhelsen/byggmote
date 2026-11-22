"""Stommen's Projekt in the knowledge base. Byggmöte administers no projects of its own: a Projekt, its Roller and the
Kontakter who hold them are Stommen's, and what Stommen says wins. A Roll is its own thing here as it is there: it can
be vacant, and one person can hold several.

`take` is given what Stommen answers for one Projekt. It does not talk to Stommen: the app signs in and fetches, the
engine keeps the knowledge base. A person is one person across projects (that is what recognises a voice), while a
Kontakt in Stommen belongs to one Projekt, so a Kontakt is matched to a person: by the link from last time, else by
e-mail, else by name."""
from . import ArgError, areas, knowledge, people
from .context import key

MAYBE = (str, type(None))


def _rows(given, name: str, allowed: dict, required: tuple) -> list[dict]:
    rows = given.get(name)
    if not isinstance(rows, list):
        raise ArgError(f"expected {name}: [...]")
    return [dict(areas.fields(x, allowed, required)) for x in rows]


def _read(given) -> tuple[dict, list[dict], list[dict]]:
    """Stommen's answer, checked: {"project": {"id", "name"}, "roles": [...], "contacts": [...]}."""
    if not isinstance(given, dict) or not isinstance(given.get("project"), dict):
        raise ArgError("expected {\"project\": {\"id\", \"name\"}, \"roles\": [...], \"contacts\": [...]}")
    project = dict(areas.fields(given["project"], {"id": str, "name": str}, ("id", "name")))
    roles = _rows(given, "roles", {"id": str, "name": str, "description": MAYBE, "holderId": MAYBE, "substituteId": MAYBE}, ("id", "name"))
    contacts = _rows(given, "contacts", {"id": str, "name": str, "organization": MAYBE, "email": MAYBE, "phone": MAYBE}, ("id", "name"))
    known = {c["id"] for c in contacts}
    for r in roles:
        if any(r.get(k) and r[k] not in known for k in ("holderId", "substituteId")):
            raise ArgError(f"the Roll {r['name']} is held by a Kontakt that is not among the contacts")
    return project, roles, contacts


def _person(ps: list[dict], pid: str, c: dict, taken: set) -> dict:
    """The person a Kontakt is: the one linked to it, else one with its e-mail, else one with its name, else new."""
    mail = (c.get("email") or "").strip().lower()
    free = [p for p in ps if p["id"] not in taken]
    p = (next((p for p in free if (p.get("stommen") or {}).get(pid) == c["id"]), None)
         or (mail and next((p for p in free if (p.get("email") or "").strip().lower() == mail), None))
         or next((p for p in free if key(p["name"]) == key(c["name"]) and pid not in (p.get("stommen") or {})), None))
    if not p:
        p = people.new(" ".join(c["name"].split()), ps)
        ps.append(p)
    return p


def take(given) -> dict:
    """One Projekt as Stommen has it, into the knowledge base: the project (made when new, renamed when Stommen renamed
    it), a person per Kontakt, and the project's Roller with who holds them. Someone who is no longer a Kontakt there
    leaves the project here; the person and the meetings they spoke at stay. Returns what the project then has."""
    project, roles, contacts = _read(given)
    pid, title = project["id"].strip(), " ".join(project["name"].split())
    if not any(a.get("stommen") == pid for a in areas.load()["areas"]):
        made = areas.add({"name": title})["id"]  # takes the lock itself
    else:
        made = None
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        a = next((a for a in cfg["areas"] if a.get("stommen") == pid or a["id"] == made), None)
        if a is None:
            raise ArgError(f"the project {title} is gone")
        a["stommen"], a["name"] = pid, title
        ps = people.load()
        who, taken = {}, set()
        for c in contacts:
            p = _person(ps, pid, c, taken)
            taken.add(p["id"])
            who[c["id"]] = p["id"]
            p["name"] = " ".join(c["name"].split())
            if (c.get("email") or "").strip():
                p["email"] = c["email"].strip()
            p["stommen"] = (p.get("stommen") or {}) | {pid: c["id"]}

        a["roles"] = [{"id": r["id"], "name": " ".join(r["name"].split()), "holder": who.get(r.get("holderId")),
                       "substitute": who.get(r.get("substituteId"))} for r in roles]
        first = {}
        for r in a["roles"]:
            if r["holder"]:
                first.setdefault(r["holder"], r["name"])

        left = []
        for p in ps:  # a Kontakt Stommen no longer has: out of the project, the person stays
            if pid in (p.get("stommen") or {}) and p["id"] not in taken:
                del p["stommen"][pid]
                if not p["stommen"]:
                    del p["stommen"]
                left.append(p["id"])
        members = [m for m in a.get("people", []) if m["person"] not in left and m["person"] not in taken]
        # Who I am is in every project without being listed in one (people.set_me).
        a["people"] = members + [{"person": p} | ({"role": first[p]} if p in first else {}) for p in who.values() if p != cfg.get("me")]
        people.save(ps)
        areas.save(cfg)
    knowledge.guides(cfg)
    return {"project": a["id"], "name": title, "people": len(who), "roles": len(roles),
            "vacant": sum(not r["holder"] for r in a["roles"]), "left": left}
