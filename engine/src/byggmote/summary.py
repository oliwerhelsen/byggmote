"""What minutes edited after the app wrote them teach (#484, #1316): swapped words become term proposals (docs/SPEC.md, Proposals)."""
import difflib
import re
from pathlib import Path

from . import areas, meeting, people
from .context import entries, key
from .suggest import clean

ORIGINAL = "summary.original.md"
SWAP = 3  # most words on either side of a swap

REASON = {"sv": 'Ändrat från "{}" i sammanfattningen.', "en": 'Changed from "{}" in the summary.'}

BOX = re.compile(r"^([ \t]*(?:[-*•]|\d+[.)])[ \t]+)\[[ xX-]\][ \t]+", re.M)


def pair(d: Path) -> tuple[str, str, Path] | None:
    """What the app wrote, the minutes now, and their file; None without both. Without the steps' boxes: a tick in the
    margin (`- [x]`, `- [-]`) isn't an edit (#780)."""
    f = meeting.minutes(d, meeting.load(d))
    try:
        return *(BOX.sub(r"\1", x.read_text(encoding="utf-8", errors="replace")) for x in (d / ORIGINAL, f)), f
    except OSError:
        return None


def swaps(before: str, after: str):
    """`(heard, term)`: one to `SWAP` words replaced by one to `SWAP` words that look like a name or term (each with a
    capital or a digit), new to the text, where the old words are gone from it everywhere. Anything else is rewriting,
    not a misheard word: a common word ("Vi" → "Erik") stays elsewhere in the text. A replacement that isn't a swap as a
    whole, with as many words on each side, is tried word by word: a fixed name next to a rewritten phrase."""
    a, b = (re.findall(r"\w[\w'’-]*", x) for x in (before, after))
    old, now = {key(w) for w in a}, f" {' '.join(key(w) for w in b)} "

    def swap(heard: list[str], new: list[str]) -> bool:
        return len(heard) <= SWAP and len(new) <= SWAP and all(any(c.isupper() or c.isdigit() for c in w) for w in new) \
            and not any(key(w) in old for w in new) and f" {' '.join(key(w) for w in heard)} " not in now

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "replace":
            continue
        pairs = [(a[i1:i2], b[j1:j2])]
        if not swap(*pairs[0]) and i2 - i1 == j2 - j1:
            pairs = [([x], [y]) for x, y in zip(a[i1:i2], b[j1:j2])]
        yield from ((" ".join(h), " ".join(n)) for h, n in pairs if swap(h, n))


def terms(d: Path, lang: str | None = None, skip: list[str] = ()) -> list[dict]:
    """Term proposals from the words swapped in the meeting's minutes."""
    p = pair(d)
    if not p or p[0] == p[1]:
        return []
    cfg, ps = areas.load(), people.load()
    area = areas.get(cfg, meeting.load(d)["area"])
    reason = REASON.get(lang or area.get("lang"), REASON["en"])
    found = [{"term": t, "heard": h, "area": area["id"], "reason": reason.format(h), "sources": [p[2].name]} for h, t in swaps(p[0], p[1])]
    return clean(found, entries(cfg, ps) + list(skip), [area["id"]], area["id"])
