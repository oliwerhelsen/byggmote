"""What a language model suggests from one done meeting (docs/SPEC.md, `terms suggest`; #482, #646): the engine gives the prompt with the
evidence, the app's model answers, and the engine cleans the answer into proposals for `byggmote learn apply`. The input is known and the run is
one model call without tools; nothing is written here.
"""
import json
import re
from pathlib import Path

from . import areas, meeting, people
from .context import Vocab, corrections, entries, heard, key, like

# Characters per part of the prompt, ~50k tokens in all.
BUDGET = {"minutes": 110_000, "transcripts": 80_000, "edits": 15_000}
MAX = 50
LANGS = {"sv": "Swedish", "en": "English"}

SCHEMA = {"type": "object", "required": ["suggestions"], "properties": {"suggestions": {"type": "array", "items": {
    "type": "object", "required": ["term", "reason", "sources"], "properties": {
        "term": {"type": "string"}, "heard": {"type": "string"}, "area": {"type": "string"},
        "person": {"type": "object", "required": ["short"], "properties": {
            "short": {"type": "string"}, "role": {"type": "string"}, "note": {"type": "string"}}},
        "reason": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}}}}}

SYSTEM = """You suggest vocabulary for context-aware dictation and transcription (Swedish and English speech \
recognition) in one meeting in the area "{area}". An entry makes the recognizer spell a name or term right, and tells the minutes and \
{user}'s agents what the area's names and terms are. Two kinds:

1. term: a name, company, product, system, abbreviation or domain term, spelled exactly as the minutes \
spell them. They are written with full context and are reliable. The transcript is raw \
speech recognition and often wrong.
2. term with heard: the recognizer writes something that does not look like the term (heard "Sea Trade" for \
cieTrade, "Kvick Books" for QuickBooks). Near misses that start the same way ("Oliver" for Oliwer, "Mikael" for \
Michael) need no heard: dictation already corrects those from the term. heard is replaced by the term everywhere, so it must be what the recognizer \
actually wrote, verbatim, seen in a transcript whose minutes spell it differently or in an edited line; \
never a common word or phrase that also means something else. One heard per suggestion.

Rules:
- Only what is specific to {user}'s areas and their people. No common Swedish or English words, no well-known names \
the recognizer already spells right in the transcript.
- A term as the speakers say it, in its base form ("fraktrater", not "fraktraterna"): never a word only the minutes use, \
a time, a date, a number or a file name.
- area: where the entry applies, "{id}" unless it is clearly general, then "everywhere" for what comes up in several areas or \
belongs to {user}'s work in general (tools, their own company).
- Nothing listed under Known, except a new heard for a known term.
- Most useful first: names and terms that come up often or that the recognizer gets wrong. At most {max}.
- person: when the entry is a person's full name: short (the name people use for them, usually the first name), \
role (their role in the area as the minutes put it, a few words in {lang}) and note (company or title, a few words), \
each only if the evidence says so. Suggest people by full name. A first name alone is neither a person nor a term.
- reason: one short sentence in {lang}. sources: the files where it was seen.
Answer only with one JSON object, no other text, that matches this JSON Schema: {schema}"""


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def known(es: list[str]) -> tuple[set, set]:
    """Keys of every term dictation already knows, lower case ones too (not boosted, #1268), and of every heard form."""
    return {key(e.partition("=")[0]) for e in es}, {"".join(h) for h, _ in Vocab(es).rules}


def user(cfg: dict, ps: list[dict]) -> str:
    """Who the areas belong to, by the `me` person's full name."""
    return next((p["name"] for p in ps if p["id"] == cfg.get("me")), "the user")


def corrected(m: dict) -> str:
    """What the transcription corrected from the vocabulary (#429), as dictation's fixes: the transcript has the terms."""
    fixes = dict.fromkeys(f"{h} → {t}" for h, t in corrections([w for g in m.get("segments", []) for w in g.get("words", [])]))
    return f"(transcription corrected: {'; '.join(fixes)})\n" if fixes else ""


def prompt(cfg: dict, ps: list[dict], area: dict, es: list[str], d: Path, m: dict, budget: int | None = None) -> str:
    """The evidence, as Markdown. `es`: what dictation already knows. `budget`: characters in all (#646), Known at most a tenth and the
    parts scaled to the rest; None: `BUDGET` as it is."""
    scale = 1 if budget is None else budget * 0.9 / sum(BUDGET.values())
    known_ = [f"- {e}" for e in dict.fromkeys(es)]
    if budget is not None:
        left = budget // 10
        known_ = [k for k in known_ if (left := left - len(k) - 1) >= 0]
    members = people.in_all_areas(cfg, ps) | {x["person"] for x in area.get("people", [])}
    roles = {x["person"]: x.get("role") for x in area.get("people", [])}
    who = [" · ".join(x for x in (p["name"], p.get("short"), roles.get(p["id"]), p.get("note")) if x)
           for p in ps if p["id"] in members]
    size = {k: int(v * scale) for k, v in BUDGET.items()}
    f = meeting.minutes(d, m)
    edits = "\n".join(f"- heard: {heard(s.get('words', []))}\n  written: {s['text']}" for s in m.get("segments", []) if s.get("edited"))
    transcript = corrected(m) + _read(d / "transcript.txt")
    return "\n\n".join([
        f"# Known\nNames and terms dictation already has or {user(cfg, ps)} skipped (heard forms after =):\n" + "\n".join(known_),
        f"# Area: {areas.name(area)} (id {area['id']})",
        "## People in the area\n" + ("\n".join(f"- {x}" for x in who) or "(none)"),
        f"## Minutes (reliable spelling): {f.name}\n" + (_read(f)[:size["minutes"]] or "(none)"),
        f"## Lines {user(cfg, ps)} corrected in the transcript\n" + (edits[:size["edits"]] or "(none)"),
        f"## Transcript (speech recognition): {d.name}\n" + (transcript[:size["transcripts"]] or "(none)"),
    ])


def clean(suggestions: list[dict], es: list[str], ids: list[str], default: str | None, ps: list[dict] = ()) -> list[dict]:
    """A model's suggestions as proposals (docs/SPEC.md, Proposals): `person` for someone not in `ps`, else `term`.
    Without what dictation already knows; one per term, heard forms joined. A heard form that looks like the term
    goes: boosting already fixes those (Oliver → Oliwer), and a replacement would apply everywhere.
    `area` is one of `ids` or None (everywhere); anything else is `default`."""
    terms, heard_ = known(es)
    people_ = {key(p["name"]) for p in ps}
    out = {}
    for s in suggestions:
        t = (s.get("term") or "").strip()
        hs = [h.strip() for h in re.split(r"[,/]", s.get("heard") or "")]
        hs = [h for h in hs if key(h) and key(h) != key(t) and key(h) not in heard_ and not like(key(h), key(t))]
        if len(key(t)) < 2 or (key(t) in terms and not hs):
            continue
        a, who = s.get("area"), s.get("person")
        who = {k: v.strip() for k, v in who.items() if k in ("short", "role", "note") and isinstance(v, str) and v.strip()} \
            if isinstance(who, dict) and key(t) not in people_ else {}
        x = out.setdefault(key(t), ({"kind": "person", "name": t} | who if who else {"kind": "term", "term": t})
                           | {"heard": [], "area": None if a == "everywhere" else a if a in ids else default,
                              "reason": (s.get("reason") or "").strip(), "sources": []})
        x["heard"] += [h for h in hs if key(h) not in {key(y) for y in x["heard"]}]
        x["sources"] += [y for y in (y.strip() for y in s.get("sources") or [] if isinstance(y, str)) if y and y not in x["sources"]]
    for x in out.values():
        if hs := x.pop("heard"):
            x["heard"] = ", ".join(hs)
    return list(out.values())[:MAX]


def _scope(d: Path, skip: list[str]):
    """What a run is about: the config, people, the meeting's area, what is known (with `skip`) and the meeting."""
    cfg, ps, m = areas.load(), people.load(), meeting.load(d)
    return cfg, ps, areas.get(cfg, m["area"]), entries(cfg, ps) + list(skip), m


def request(d: Path, lang: str | None = None, skip: list[str] = (), budget: int | None = None) -> dict:
    """The system prompt, the evidence and the schema for the model; fewer suggestions asked for with a `budget`."""
    cfg, ps, area, es, m = _scope(d, skip)
    most = MAX if budget is None else min(MAX, max(10, budget // 3000))
    system = SYSTEM.format(area=areas.name(area), id=area["id"], max=most, lang=LANGS.get(lang or area.get("lang"), "English"),
                           user=user(cfg, ps), schema=json.dumps(SCHEMA))
    return {"system": system, "prompt": prompt(cfg, ps, area, es, d, m, budget), "schema": SCHEMA}


def answer(d: Path, suggestions: list[dict], skip: list[str] = ()) -> list[dict]:
    """The model's suggestions (`read`) as proposals."""
    cfg, ps, area, es, _ = _scope(d, skip)
    return clean(suggestions, es, [a["id"] for a in cfg["areas"]], area["id"], ps)


def read(text: str) -> list[dict]:
    """The suggestions in a model's answer: JSON, maybe in a code fence or with words around it, `{"suggestions": [...]}`
    or the list alone."""
    t, out = text.strip(), None
    for i, j in ((0, len(t) - 1), (t.find("{"), t.rfind("}")), (t.find("["), t.rfind("]"))):
        try:
            out = json.loads(t[i:j + 1]) if 0 <= i < j else None
        except json.JSONDecodeError:
            continue
        if out is not None:
            break
    if isinstance(out, dict):
        out = out.get("suggestions")
    if not isinstance(out, list):
        raise ValueError("unreadable answer: " + (t[:200] or "(empty)"))
    return [x for x in out if isinstance(x, dict)]
