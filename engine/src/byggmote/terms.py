"""An area's names and terms (SPEC.md, Editing the knowledge base): add, change or delete a line in `vocabulary`."""

from . import areas, people


FIELDS = {"term": str, "heard": list, "area": (str, type(None))}


def _place(cfg: dict, area: str | None) -> dict:
    """Where an area's lines are: the root for null (everywhere)."""
    return cfg if area is None else areas.get_known(cfg, area)


def _known(cfg: dict, ps: list[dict], given) -> tuple[dict, int]:
    """The line `given` ({"term", "area"}) names: its place and index. A person's line is their Sounds like (`people set`)."""
    from . import ArgError
    from .learn import _line
    if not isinstance(given, dict) or set(given) != {"term", "area"} or not isinstance(given["term"], str) \
            or not isinstance(given["area"], (str, type(None))):
        raise ArgError("expected {\"term\": TEXT, \"area\": ID or null}")
    h = _place(cfg, given["area"])
    i = _line(h.get("vocabulary") or [], given["term"])
    if i is None:
        raise ArgError(f"unknown term: {given['term']}")
    if len([p for p in ps if people._named(p, given["term"])]) == 1:
        raise ArgError(f"{given['term']} is a person's Sounds like: people set")
    return h, i


def _line_out(line: str, area: str | None) -> dict:
    from .learn import _split
    t, heard = _split(line)
    return {"term": t, "heard": heard, "area": area}


def _term(f: dict) -> str:
    from . import ArgError
    t = f["term"].strip()
    if not t or "=" in t:
        raise ArgError("term: expected text without =")
    return t


def _put(h: dict, term: str, heard: list[str]) -> str:
    """`term = heard` into place `h`, as Byggmöte's `Term.save`: a line with the term there takes the spelling and the heard forms
    joined, once each (#769); else a new line at the end. The line written."""
    from .learn import _entry, _set, _split, key
    lines = list(h.get("vocabulary") or [])
    i = next((i for i, e in enumerate(lines) if key(_split(e)[0]) == key(term)), None)
    if i is None:
        lines.append(_entry(term, people._unique(heard)))
        i = len(lines) - 1
    else:
        lines[i] = _entry(term, people._unique(_split(lines[i])[1] + heard))
    _set(h, lines)
    return lines[i]


def add(given) -> dict:
    from . import knowledge
    f = areas.fields(given, FIELDS, ("term",))
    t, heard = _term(f), people._heard(f) or []
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        line = _put(_place(cfg, f.get("area")), t, heard)
        areas.save(cfg)
    return _line_out(line, f.get("area"))


def set_term(given) -> dict:
    """The line `was` names, changed: a new spelling, heard forms (the whole list) or place. As Byggmöte's `Term.save`: the term already
    in the new place takes it (#769) and this line goes; else the line changes where it is, or goes last in its new place."""
    from . import ArgError, knowledge
    from .learn import _entry, _set, _split, key
    f = areas.fields(given, FIELDS | {"was": dict})
    if "was" not in f:
        raise ArgError("missing was")
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        old, i = _known(cfg, people.load(), f["was"])
        lines = list(old["vocabulary"])
        spelled, had = _split(lines.pop(i))
        _set(old, lines)
        t = _term(f) if "term" in f else spelled
        heard = people._heard(f) if "heard" in f else had
        area = f["area"] if "area" in f else f["was"]["area"]
        h = _place(cfg, area)
        if h is old and not any(key(_split(e)[0]) == key(t) for e in lines):
            line = _entry(t, people._unique(heard))
            _set(old, lines[:i] + [line] + lines[i:])
        else:
            line = _put(h, t, heard)
        areas.save(cfg)
    return _line_out(line, area)


def delete(given) -> dict:
    from . import knowledge
    from .learn import _set
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        h, i = _known(cfg, people.load(), given)
        lines = list(h["vocabulary"])
        line = lines.pop(i)
        _set(h, lines)
        areas.save(cfg)
    return _line_out(line, given["area"])
