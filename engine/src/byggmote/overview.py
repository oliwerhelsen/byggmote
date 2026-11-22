"""What the app lists: the projects with their people and series, a project's meetings, and one meeting with its
transcript and protocol. Read only, so the app shows what the engine's files say without knowing how they are kept."""
from pathlib import Path

from . import areas, knowledge, meeting, people, protocol, series, stommen


def projects() -> dict:
    """Every project but the fallback, with who holds which Roll, the Roller there are to choose from (a vacant one
    too, in a Projekt of Stommen's), the Projekt's id in Stommen when it is Stommen's, and the series' next numbers."""
    cfg = areas.load()
    names = {p["id"]: p["name"] for p in people.load()}
    return {"folder": str(knowledge.folder()), "projects": [
        {"id": a["id"], "name": a["name"], "stommen": a.get("stommen"), "roles": protocol.roles(a),
         "people": [{"id": pid, "name": names[pid]} | ({"role": protocol.held(a)[pid]} if pid in protocol.held(a) else {})
                    for pid in dict.fromkeys([x["person"] for x in a.get("people", [])] + list(protocol.held(a))) if pid in names],
         "series": [{"id": s["id"], "name": s["name"], "next": series.next_no(s)} for s in series.load(a)["series"]]}
        for a in cfg["areas"] if a["id"] != areas.DEFAULT]}


def _filed(area: dict) -> dict:
    """Each filed meeting's folder to (series id, number)."""
    return {d.resolve(): (s["id"], no) for s in series.load(area)["series"] for no, d in series.meetings(area, s)}


def _row(d: Path, m: dict, filed: tuple | None) -> dict:
    said = {g["speaker"] for g in m["segments"]}
    try:
        p = protocol.load(d)
        pts = (p or {}).get("points", [])
        about = p and {"status": p.get("status"), "points": sum("since" not in x for x in pts), "carried": sum("since" in x for x in pts),
                       "open": sum(bool(x.get("open")) for x in pts), "checks": sum(len(protocol.unchecked(x)) for x in pts)}
    except ValueError:  # a protocol nobody can read is shown as that, not as no protocol
        about = {"status": "unreadable"}
    return {"dir": str(d), "title": m.get("title", ""), "recorded_at": m.get("recorded_at"), "duration": m.get("duration", 0),
            "status": m.get("status"), "error": m.get("error"), "series": filed and filed[0], "no": filed and filed[1],
            "unnamed": sum(s["id"] in said and not s.get("person") and s["name"].startswith(meeting.UNNAMED) for s in m["speakers"]),
            "protocol": about}


def meetings(area_id: str) -> list[dict]:
    """The project's meetings, the latest first."""
    cfg = areas.load()
    filed = _filed(areas.get_known(cfg, area_id))
    rows = [_row(d, m, filed.get(d.resolve())) for d, m in meeting.everywhere(cfg) if m.get("area") == area_id]
    return sorted(rows, key=lambda x: x["recorded_at"] or "", reverse=True)


def detail(d: Path) -> dict:
    """One meeting: its row, the transcript's lines with who says them, and the whole protocol. With a protocol:
    `corrections`, how much of it a person has set right, and `later`, the meeting that builds on it, if one does
    (then it is neither corrected nor written again), and `stommen`, where the protocol stands with Stommen."""
    d = Path(d).expanduser()
    m = meeting.load(d)
    area = areas.get(areas.load(), m["area"])
    p = protocol.load(d)
    names = {s["id"]: s for s in m["speakers"]}
    said = list(dict.fromkeys(g["speaker"] for g in m["segments"]))
    return _row(d, m, _filed(area).get(d.resolve())) | {
        "project": area["id"], "audio": (d / "audio.m4a").is_file(),
        "speakers": [{"id": i, "name": names[i]["name"], "person": names[i].get("person")} for i in said if names[i]["name"] != meeting.IGNORED],
        "lines": [{"id": g["id"], "at": g["start"], "speaker": g["speaker"], "who": names[g["speaker"]]["name"], "text": g["text"]}
                  for g in m["segments"] if names[g["speaker"]]["name"] != meeting.IGNORED],
        "protocol": p, "corrections": protocol.corrections(p or {}), "stommen": stommen.sending(d, p, area) if p else None,
        "later": protocol.later(area, series.get(series.load(area), p["series"]), p["no"]) if p else None}
