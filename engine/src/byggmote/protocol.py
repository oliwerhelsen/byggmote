"""The byggmötesprotokoll: what a language model reads out of a transcript, checked against it and numbered here.

The model proposes, this module decides what is shown. A point is kept only when its quote is in the transcript, and
then it points at the line where that is said: no source, nothing shown. The numbers (<meeting>.<heading>.<n>) are
set here, never by the model, and a point an earlier meeting left open follows along under its own number until a
meeting closes it. An amount always carries a check with the words the recording has, for a person to confirm.
`protocol.json` is the record, `protocol.md` the same for reading."""
import difflib
import json
import re
from datetime import date, datetime
from pathlib import Path

from . import ArgError, areas, atomic_write, knowledge, meeting, people, read_json, series
from .context import key

FILE, TEXT, MARKS = "protocol.json", "protocol.md", "marks.json"
SCHEMA = 1
# The kinds by their code names in Stommen's glossary, and what the protocol calls them.
KINDS = {"decision": "Beslut", "todo": "Att göra", "changeOrder": "ÄTA", "deviation": "Avvikelse",
         "question": "Fråga", "risk": "Risk", "note": "Notering"}
CLOSED = ("decision", "note")  # said and done at the meeting: never on a later agenda
WEEKDAYS = ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag")
QUOTE = (3, 15)  # the words and letters a quote needs: a shorter one is in any meeting somewhere
ALIKE = 0.8  # the share of a quote's letters a line must have, in the quote's order
RUN = 5  # in runs of at least this many: shorter runs match by chance
AMOUNT = re.compile(r"(?<![\w.,])(?:\d{1,3}(?:[  .]\d{3})+|\d+)(?:,\d+)?\s*(?:kr|kronor|tkr|mkr|sek|tusen|miljoner|miljarder)\b", re.I)

RULES = """Så här gör du:
- Gå igenom dagordningens rubriker i tur och ordning och ta med det som sägs under var och en. Även ett läge eller en upplysning är en punkt: hur tidplanen ligger till, att föregående protokoll är justerat, när nästa möte hålls.
- Ta bara med det som sägs i utskriften. Lägg inte till något och gissa inte.
- En punkt är en sak, skriven som en eller två korta, sakliga meningar på svenska. Belopp skrivs med siffror och enhet, som 86 500 kr.

Fälten i en punkt:
- "heading": numret på rubriken där punkten hör hemma.
- "kind": ett av följande.
  "decision": ett beslut som fattas på mötet.
  "todo": något som någon ska göra.
  "changeOrder": en ÄTA, alltså ett ändrat, tillkommande eller avgående arbete som påverkar pris eller tid.
  "deviation": en avvikelse från handlingarna, till exempel att byta en föreskriven produkt mot en annan, eller en begäran om det.
  "question": en fråga som behöver svar från någon.
  "risk": något som kan gå fel.
  "note": ett läge eller en upplysning.
- "role": den Roll som ska göra det eller svara, skriven precis som i listan över roller. Den som talar är inte alltid den som ansvarar. null om det inte framgår. Aldrig ett personnamn.
- "due": datumet som ÅÅÅÅ-MM-DD om en dag eller ett datum sägs, annars null.
- "open": true om något återstår att göra, besvara eller besluta efter mötet, annars false.
- "time": tidsstämpeln på raden där det sägs.
- "quote": fem till femton ord i följd, ordagrant ur den raden, så att stället går att hitta. Ändra inga ord i citatet.

Öppna punkter från tidigare möten:
- När mötet talar om just den sak som en öppen punkt gäller skriver du en post i "carried" i stället för en ny punkt. "no" är punktens nummer. "text" är det som sägs om den på det här mötet, inte punktens gamla text. "open" är false om den är klar eller utgår, annars true. "due" är ett nytt datum om ett sägs.
- En öppen punkt som inte nämns tar du inte med. Det som står i "carried" upprepas inte i "points".

Svara med ett JSON-objekt och inget annat, i den här formen:
{"carried": [{"no": "<punktens nummer>", "text": "…", "role": null, "due": null, "open": true, "time": "<tid>", "quote": "…"}],
 "points": [{"heading": <rubrikens nummer>, "kind": "<typ>", "text": "…", "role": null, "due": null, "open": false, "time": "<tid>", "quote": "…"}]}
"""


def order(no: str) -> tuple:
    """A point's number as it sorts: 3.4.2 before 3.4.10 before 5.1.1."""
    return tuple(int(x) for x in no.split("."))


def load(d: Path) -> dict | None:
    """The meeting's protocol, None when it has none."""
    p = Path(d) / FILE
    return read_json(p, "no", "points") if p.exists() else None


def open_points(area: dict, s: dict, before: int) -> list[dict]:
    """The points no meeting before number `before` has closed, as the last meeting that had them left them, by number.
    A protocol that can't be read stops it: a point must not fall off the agenda unseen."""
    state = {}
    for no, d in series.meetings(area, s):
        p = load(d) if no < before else None
        for x in (p or {}).get("points", []):
            if x.get("open"):
                state[x["no"]] = {k: x.get(k) for k in ("no", "heading", "kind", "text", "role", "due")}
            else:
                state.pop(x["no"], None)
    return sorted(state.values(), key=lambda x: order(x["no"]))


def lines(m: dict) -> list[dict]:
    """The transcript's lines as the model reads them; an ignored speaker's are left out."""
    names = {s["id"]: s["name"] for s in m["speakers"]}
    return [{"id": g["id"], "at": g["start"], "who": names[g["speaker"]], "text": g["text"]}
            for g in m["segments"] if names[g["speaker"]] != meeting.IGNORED]


def seconds(stamp) -> int | None:
    """`17:42`, `1:02:03` or `[17:42]` in seconds; None for anything else."""
    hit = re.fullmatch(r"\[?(?:(\d+):)?(\d{1,3}):(\d\d)\]?", stamp.strip()) if isinstance(stamp, str) else None
    return int(hit[1] or 0) * 3600 + int(hit[2]) * 60 + int(hit[3]) if hit else None


def locate(ls: list[dict], stamp, quote) -> dict | None:
    """The line a point's quote is in, the one nearest the time the model gave: the model's time alone proves nothing.
    A quote that runs on into the next line belongs to the first. None when the quote is too short or nowhere."""
    q, t = key(str(quote or "")), seconds(stamp)
    if len(str(quote or "").split()) < QUOTE[0] or len(q) < QUOTE[1]:
        return None
    texts = [key(x["text"]) for x in ls]
    hits = [x for x, a in zip(ls, texts) if _has(a, q)] or [x for x, a, b in zip(ls, texts, texts[1:]) if _has(a + b, q)]
    if not hits:
        return None
    return min(hits, key=lambda x: abs(x["at"] - t)) if t is not None else hits[0]


def _has(text: str, q: str) -> bool:
    """`text` has the quote `q`, both as letters and digits only (86 500 is 86.500): ALIKE of the quote's, in its order,
    in runs of RUN or more. A word the model respelled does not lose the place; other words in another order do."""
    blocks = difflib.SequenceMatcher(None, q, text, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= RUN) >= ALIKE * len(q)


def roles(area: dict) -> list[str]:
    """The project's roles, once each, in the order of its people."""
    return list(dict.fromkeys(x["role"] for x in area.get("people", []) if x.get("role")))


def attendees(m: dict, area: dict, ps: list[dict]) -> list[dict]:
    """Who spoke: a named person with their Roll in the project, anyone else under the name the meeting has."""
    said, names = {g["speaker"] for g in m["segments"]}, {p["id"]: p["name"] for p in ps}
    role = {x["person"]: x.get("role") for x in area.get("people", [])}
    out = []
    for sp in m["speakers"]:
        if sp["id"] not in said or sp["name"] == meeting.IGNORED:
            continue
        pid = sp.get("person") if sp.get("person") in names else None
        e = {"name": names[pid] if pid else sp["name"]} | ({"role": role[pid]} if pid and role.get(pid) else {})
        if e not in out:
            out.append(e)
    return out


def _text(v) -> str:
    return " ".join(v.split()) if isinstance(v, str) else ""


def _role(given, known: dict) -> tuple[str | None, list[dict]]:
    """The Roll the model named, as the project spells it. One the project lacks is a check for a person, never a guess."""
    g = _text(given)
    if not g or key(g) in known:
        return known.get(key(g)), []
    return None, [{"code": "role", "said": g}]


def _due(given) -> str | None:
    try:
        return date.fromisoformat(given).isoformat() if isinstance(given, str) else None
    except ValueError:
        return None


def _checks(text: str, line: dict) -> list[dict]:
    """An amount in a point is read by a person against what the recording has, every time."""
    return [{"code": "amount", "value": " ".join(a.group(0).split()), "said": line["text"]} for a in AMOUNT.finditer(text)]


def _dropped(reason: str, text: str, x: dict) -> dict:
    """What the model proposed and the protocol does not show, with the source it gave, for a person who wonders why."""
    return {"reason": reason, "text": text, "time": _text(x.get("time")) or None, "quote": _text(x.get("quote")) or None}


def build(m: dict, area: dict, s: dict, no: int, answer: dict, prior: list[dict], ps: list[dict], model: str | None = None) -> dict:
    """The protocol of meeting `no` from the model's `answer` and the points earlier meetings left open (`prior`)."""
    ls, heads, known, dropped = lines(m), {h["no"]: h for h in s["headings"]}, {key(r): r for r in roles(area)}, []
    new = []
    for x in answer.get("points") or []:
        text = _text(x.get("text")) if isinstance(x, dict) else ""
        if not text:
            continue
        h = x.get("heading")
        if isinstance(h, bool) or h not in heads or heads[h].get("fill"):
            dropped.append(_dropped("heading", text, x))
            continue
        line = locate(ls, x.get("time"), x.get("quote"))
        if not line:
            dropped.append(_dropped("no-source", text, x))
            continue
        kind = x.get("kind") if x.get("kind") in KINDS else "note"
        # A risk is not closed by the words that raise it. Only what stays open has someone to do it and a day.
        still = kind == "risk" or kind not in CLOSED and x.get("open") is not False
        role, checks = _role(x.get("role"), known) if still else (None, [])
        new.append({"heading": h, "kind": kind, "text": text, "role": role, "due": _due(x.get("due")) if still else None,
                    "open": still, "at": line["at"], "line": line["id"],
                    "quote": _text(x.get("quote")), "checks": checks + _checks(text, line)})
    count = {}
    for x in sorted(new, key=lambda x: (x["heading"], x["at"])):
        count[x["heading"]] = count.get(x["heading"], 0) + 1
        x["no"] = f"{no}.{x['heading']}.{count[x['heading']]}"

    by, raised = {p["no"]: p for p in prior}, {}
    for x in answer.get("carried") or []:
        if not isinstance(x, dict) or x.get("no") in raised:
            continue
        text = _text(x.get("text"))
        if x.get("no") not in by:
            dropped.append(_dropped("unknown-point", text, x) | {"no": x.get("no")})
            continue
        line = locate(ls, x.get("time"), x.get("quote"))
        if not line or not text:
            # A model lists a point that was not taken up, with nothing new and no source the transcript has: that is
            # no proposal. One that closes the point or says something about it is, and a person may wonder where it went.
            if x.get("open") is False or text and key(text) != key(by[x["no"]]["text"]):
                dropped.append(_dropped("no-source", text, x) | {"no": x["no"]})
            continue
        raised[x["no"]] = (x, text, line)
    carried = []
    for p in prior:
        base = {k: p.get(k) for k in ("no", "heading", "kind", "text", "role", "due")} | {"since": order(p["no"])[0]}
        if p["no"] not in raised:  # not taken up, or nothing said that the transcript has: it stays as it was
            carried.append(base | {"open": True, "raised": False, "follow": None, "said": None, "at": None, "line": None,
                                   "quote": None, "checks": []})
            continue
        x, text, line = raised[p["no"]]
        role, checks = _role(x.get("role"), known)
        # `follow` is what the meeting says about the point. A model that only repeats the point says nothing: the line itself is shown.
        carried.append(base | {"role": role or p.get("role"), "due": _due(x.get("due")) or p.get("due"),
                               "open": x.get("open") is not False, "raised": True,
                               "follow": text if key(text) != key(p["text"]) else None, "said": line["text"], "at": line["at"],
                               "line": line["id"], "quote": _text(x.get("quote")), "checks": checks + _checks(text, line)})
    return {"schema": SCHEMA, "series": s["id"], "name": s["name"], "no": no, "status": "draft", "model": model,
            "written_at": meeting.now(), "headings": [dict(h) for h in s["headings"]], "attendees": attendees(m, area, ps),
            "points": sorted(carried + new, key=lambda x: (x["heading"], order(x["no"]))), "dropped": dropped}


def _sentence(t: str) -> str:
    return t if t[-1:] in ".!?" else t + "."


def _point(x: dict, name: str) -> list[str]:
    who = (f" Ansvarig: {x['role']}." if x.get("role") else "") + (f" Senast {x['due']}." if x.get("due") else "")
    at = f" [{meeting.clock(x['at'])}]" if x.get("at") is not None else ""
    if "since" in x:
        state = "kvarstår" if x["open"] else "avslutad"
        out = [f"- **{x['no']}** {KINDS[x['kind']]}, {state} från {name} {x['since']}. {_sentence(x['text'])}{who}",
               "  - Togs inte upp på mötet." if not x["raised"] else
               f"  - På mötet: {_sentence(x['follow'])}{at}" if x["follow"] else f"  - På mötet sägs: ”{x['said']}”{at}"]
    else:
        out = [f"- **{x['no']}** {KINDS[x['kind']]}. {_sentence(x['text'])}{who}{at}"]
    for c in x.get("checks", []):
        if c["code"] == "amount":
            out.append(f"  - Kontrollera beloppet {c['value']}. I inspelningen sägs: ”{c['said']}”")
        elif c["code"] == "role":
            out.append(f"  - Rollen ”{c['said']}” finns inte i projektet. Välj Roll.")
    return out


def render(p: dict, m: dict, project: str) -> str:
    """protocol.md: every heading in order, the points under theirs, each with the time it is said."""
    name = p["name"].lower()
    day = datetime.fromisoformat(m["recorded_at"])
    out = [f"# Protokoll, {name} {p['no']}", "",
           f"{project}. {day:%Y-%m-%d}, {max(1, round(m['duration'] / 60))} minuter."
           + (" Utkast, inte justerat." if p["status"] == "draft" else ""), ""]
    for h in p["headings"]:
        out += [f"## {h['no']}. {h['name']}", ""]
        if h.get("fill") == "attendees":
            out += [f"- {a['name']}" + (f", {a['role']}" if a.get("role") else "") for a in p["attendees"]] or ["Ingen talare i inspelningen."]
        else:
            out += [row for x in p["points"] if x["heading"] == h["no"] for row in _point(x, name)] or ["Inget noterat."]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def prepare(d: Path, sid: str, no: int | None) -> tuple:
    """What a protocol is written from: the meeting, its project, the series, the meeting's number there (its own
    when filed, else `no` or the next), the points left open before it, and the people."""
    m = meeting.load(d)
    if m.get("status") in ("processing", "failed"):
        raise ValueError("the meeting has no transcript")
    area = areas.get(areas.load(), m["area"])
    s = series.get(series.load(area), sid)
    n = no if no is not None else series.filed(area, s, d) or series.next_no(s)
    return m, area, s, n, open_points(area, s, n), people.load()


def _marks(d: Path) -> dict:
    """What was pressed while recording: {"headings": [{"no", "at"}], "marks": [{"kind", "at"}]}. A help, never needed."""
    try:
        obj = json.loads((d / MARKS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def schema(s: dict, area: dict, prior: list[dict]) -> dict:
    """The answer's JSON schema, for a model that can be held to one: then a heading, a kind, a Roll and an open point's
    number can only be ones there are. `build` checks the same things for a model that cannot."""
    text, maybe = {"type": "string"}, lambda t: {"anyOf": [t, {"type": "null"}]}
    own = {"text": text, "role": maybe({"type": "string", "enum": roles(area)}) if roles(area) else {"type": "null"},
           "due": maybe({"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}), "open": {"type": "boolean"},
           "time": text, "quote": text}

    def item(first: dict) -> dict:
        return {"type": "object", "properties": first | own, "required": [*first, *own], "additionalProperties": False}

    point = item({"heading": {"type": "integer", "enum": [h["no"] for h in s["headings"] if not h.get("fill")]},
                  "kind": {"type": "string", "enum": list(KINDS)}})
    carried = {"type": "array", "items": item({"no": {"type": "string", "enum": [p["no"] for p in prior]}})} if prior \
        else {"type": "array", "maxItems": 0}
    return {"type": "object", "properties": {"carried": carried, "points": {"type": "array", "items": point}},
            "required": ["carried", "points"], "additionalProperties": False}


def request(d: Path, sid: str, no: int | None = None) -> dict:
    """What a model is asked for the meeting's protocol, the local one or any other: {"no", "prompt", "schema"}."""
    d = Path(d).expanduser()
    m, area, s, n, prior, ps = prepare(d, sid, no)
    day = datetime.fromisoformat(m["recorded_at"])
    heads = {h["no"]: h for h in s["headings"]}
    agenda = [f"{h['no']}. {h['name']}" + (" (fylls i av programmet, skriv inga punkter här)" if h.get("fill")
                                           else f": {h['hint']}" if h.get("hint") else "") for h in s["headings"]]
    still = [f"- {p['no']} (rubrik {p['heading']}, {KINDS[p['kind']]}"
             + (f", ansvarig {p['role']}" if p.get("role") else "") + (f", senast {p['due']}" if p.get("due") else "")
             + f"): {p['text']}" for p in prior]
    who = [f"- {a['name']}" + (f", {a['role']}" if a.get("role") else "") for a in attendees(m, area, ps)]
    pressed = sorted([(x["at"], f"(Här trycktes rubrik {x['no']}. {heads[x['no']]['name']})") for x in _marks(d).get("headings", [])
                      if isinstance(x, dict) and x.get("no") in heads and isinstance(x.get("at"), (int, float))]
                     + [(x["at"], f"(Här sattes märket {KINDS[x['kind']]})") for x in _marks(d).get("marks", [])
                        if isinstance(x, dict) and x.get("kind") in KINDS and isinstance(x.get("at"), (int, float))])
    body = []
    for x in lines(m):
        while pressed and pressed[0][0] <= x["at"]:
            body.append(pressed.pop(0)[1])
        body.append(f"[{meeting.clock(x['at'])}] {x['who']}: {x['text']}")
    head = "\n".join([
        f"Du skriver protokollet för {s['name'].lower()} {n} i projektet {areas.name(area)}. "
        f"Mötet hölls {WEEKDAYS[day.weekday()]} {day:%Y-%m-%d}.", "",
        "Dagordningens rubriker:", *agenda, "",
        "Roller i projektet: " + (", ".join(roles(area)) or "inga angivna"), "",
        "Närvarande:", *(who or ["- okänt"]), "",
        "Öppna punkter från tidigare möten:", *(still or ["- inga"]), "",
        RULES, "Utskrift:", ""])
    return {"no": n, "prompt": head + "\n".join(body) + "\n\nSvara nu med JSON-objektet.\n", "schema": schema(s, area, prior)}


def read(text: str) -> dict:
    """The model's answer as {"points", "carried"}; ValueError when it is not that."""
    i, j = text.find("{"), text.rfind("}")
    try:
        obj = json.loads(text[i:j + 1]) if 0 <= i < j else None
    except json.JSONDecodeError as e:
        raise ValueError(f"the model's answer is not JSON: {e}") from None
    if not isinstance(obj, dict) or not all(isinstance(obj.get(k, []), list) for k in ("points", "carried")):
        raise ValueError("the model's answer has no points")
    return obj


def answer(d: Path, sid: str, text: str, no: int | None = None, model: str | None = None) -> dict:
    """The model's answer becomes the meeting's protocol, and the meeting takes its number in the series. A protocol
    a later meeting builds on is not written again: its points' numbers are on that meeting's agenda."""
    d, found = Path(d).expanduser(), read(text)
    with knowledge.locked(knowledge.folder()):
        m, area, s, n, prior, ps = prepare(d, sid, no)
        if n < 1:
            raise ArgError(f"bad meeting number: {n}")
        if later := [k for k, x in series.meetings(area, s) if k > n and (x / FILE).exists()]:
            raise ArgError(f"{s['name']} {later[0]} builds on this protocol")
        n = series.file(area, sid, d, n)
        p = build(m, area, s, n, found, prior, ps, model)
        atomic_write(d / FILE, json.dumps(p, ensure_ascii=False, indent=1) + "\n")
        atomic_write(d / TEXT, render(p, m, areas.name(area)))
    pts = p["points"]
    return {"dir": str(d), "series": sid, "no": n, "points": sum("since" not in x for x in pts),
            "carried": sum("since" in x for x in pts), "open": sum(x["open"] for x in pts),
            "checks": sum(len(x["checks"]) for x in pts), "dropped": p["dropped"]}
