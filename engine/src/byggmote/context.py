"""Context-aware dictation and meetings: the vocabulary (people, areas, `vocabulary` in areas.json) and how it
corrects words.

A boosted decode is biased towards the terms but also invents them (measured in #329: "Ja, det är" → "Julia"),
so its words are kept only where they spell a term and look like what the plain decode heard.
`term = heard, heard` in a vocabulary is a replacement: for names nothing like how they sound (cieTrade).
A corrected word keeps what was heard in `heard` (#429); a term of several words keeps it on its first word,
the rest get "".
A term in lower case is an ordinary word, which the plain decode spells: it is not boosted, only its heard forms apply (#1268).
"""
import difflib
import re
import sys
import traceback
from pathlib import Path

from . import areas, people, read_json

LIKE = 0.7  # Oliver/Oliwer 0.83, Cloud/Claude 0.73, Ecuman/Ekman 0.73; till/Tim 0.57 must not trigger
PUNCT = ".,!?:;"
# Common function words: how `run` tells Swedish from English, and words that are no part of a name (#429)
SV = set("och att det som är jag på för med har inte en ett vi till av om så den du men kan ska var de här nu också eller hur vad alla från när bara mycket någon".split())
EN = set("the and to of is that it you we for on with are this be have not but can what will they there so just do at our was about right then".split())


def key(s: str) -> str:
    return re.sub(r"[^\w]|_", "", s.lower())


def like(a: str, b: str) -> bool:
    if not a or not b or a[0] != b[0] or a == b:
        return False
    m = difflib.SequenceMatcher(None, a, b)
    return m.real_quick_ratio() >= LIKE and m.quick_ratio() >= LIKE and m.ratio() >= LIKE


class Vocab:
    def __init__(self, entries: list[str], meeting: bool = False):
        """`meeting` (#429): boost only around words near a term, with two more guards against invented names.
        Dictation keeps its #329 behaviour: on 882 of Tim's dictations it corrected 3 more names and invented 1. Neither
        boosts a lower-case term (#1268)."""
        self.meeting = meeting
        self.terms, self.rules, self.known = [], [], set()  # rules: (heard keys, term); known: every name and term, and their words
        for e in entries:
            term, _, heard = (x.strip() for x in e.partition("="))
            if len(key(term)) < 2:
                continue
            self.known |= {key(w) for w in [term, *term.split()]}
            if heard:
                self.rules += [(tuple(key(w) for w in h.split()), term) for h in re.split(r"[,/]", heard) if key(h)]  # / before #348
            elif term not in self.terms and term != term.lower():
                self.terms.append(term)
        self.keys = {key(t): t for t in self.terms}
        self.longest = max((len(t.split()) for t in self.terms), default=0)

    def near(self, words: list[str]) -> list[tuple[int, int]]:
        """Spans `(i, j)` of plain words that look like a term without being one: only there is the boosted decode
        worth it."""
        ks = [key(w) for w in words]
        return [(i, i + n) for i in range(len(ks)) for n in range(1, self.longest + 1)
                if i + n <= len(ks) and any(like("".join(ks[i:i + n]), k) for k in self.keys)]

    def merge(self, plain: list[dict], boosted: list[dict]) -> tuple[list[dict], list[dict]]:
        """Plain words, with boosted spans that are a term and look like the plain span. Also the fixes made."""
        out, fixes = [], []
        ops = difflib.SequenceMatcher(None, [key(w["w"]) for w in plain], [key(w["w"]) for w in boosted]).get_opcodes()
        for op, i1, i2, j1, j2 in ops:
            if op == "equal":
                out += plain[i1:i2]
            else:
                self._pick(plain[i1:i2], boosted[j1:j2], out, fixes)
        return out, fixes

    def _pick(self, a: list[dict], b: list[dict], out: list, fixes: list):
        """The first term in `b` that looks like a span of `a`; the words around it the same way, recursively."""
        for j in range(len(b)):
            for n in range(1, min(self.longest, len(b) - j) + 1):
                kt = key("".join(w["w"] for w in b[j:j + n]))
                if kt not in self.keys:
                    continue
                for i in range(len(a)):
                    for m in range(1, min(n + 1, len(a) - i) + 1):
                        h = a[i:i + m]
                        ka = key("".join(w["w"] for w in h))
                        # "duktig på cloud": a word the model wrote in lower case is not a name
                        if not like(ka, kt) or (a[i]["w"][:1].islower() and b[j]["w"][:1].isupper()):
                            continue
                        # "Living at" is not LivingIT (#1072): a term that adds two letters or more to all that was
                        # heard adds what was not said; one is a lost sound (Ekma: Ekman)
                        if kt.startswith(ka) and len(kt) - len(ka) > 1:
                            continue
                        # "matchmakingen" is matchmaking already, inflected; "And he's" is not Andreas: words this
                        # common are no part of a name split in two
                        if self.meeting and (ka.startswith(kt) or m > n and any(key(w["w"]) in SV | EN for w in h)):
                            continue
                        self._pick(a[:i], b[:j], out, fixes)
                        out += self._term(b[j:j + n], h, ka.endswith("s") and not kt.endswith("s"), fixes)
                        self._pick(a[i + m:], b[j + n:], out, fixes)
                        return
        out += a

    @staticmethod
    def _term(t: list[dict], a: list[dict], genitive: bool, fixes: list) -> list[dict]:
        """Boosted words `t` for the heard words `a`: their times (a meeting sorts words by time) and their
        punctuation; a heard genitive-s stays (Ekmans)."""
        lo, hi = a[0]["s"], a[-1]["e"]
        t = [w | {"s": min(max(w["s"], lo), hi), "e": min(max(w["e"], lo), hi)} for w in t]
        t[0]["s"], t[-1]["e"] = lo, hi
        tail = a[-1]["w"][len(a[-1]["w"].rstrip(PUNCT)):]
        t[-1]["w"] = t[-1]["w"].rstrip(PUNCT) + ("s" if genitive and len(t) == 1 else "") + tail
        fix = {"from": heard(a), "to": " ".join(w["w"] for w in t)}
        if fix["from"] == fix["to"]:
            return t
        fixes.append(fix)
        return mark(t, fix["from"])

    def replace(self, words: list[dict]) -> tuple[list[dict], list[dict]]:
        """Heard forms become their term: exactly, or one letter off (Seedrade for Seedrad). Looser matched
        ordinary words in #350 (Gira: göra, Sea Trade: ser det)."""
        out, fixes, i = [], [], 0
        ks = [key(w["w"]) for w in words]
        while i < len(words):
            hit = next(((h, t) for h, t in self.rules if tuple(ks[i:i + len(h)]) == h), None) \
                or next(((h, t) for h, t in self.rules if self._close(ks[i:i + len(h)], h)), None)
            if not hit:
                out.append(words[i])
                i += 1
                continue
            rule, term = hit
            n = len(rule)
            last = words[i + n - 1]["w"]
            core = last.rstrip(PUNCT)
            genitive = "".join(ks[i:i + n]) == "".join(rule) + "s" and not term.endswith("s")  # Olivers: Oliwers
            w, h = term + ("s" if genitive else "") + last[len(core):], heard(words[i:i + n])
            fixes.append({"from": h, "to": w})
            out.append({"w": w, "s": words[i]["s"], "e": words[i + n - 1]["e"], "heard": h})
            i += n
        return out, fixes

    def _close(self, ks: list[str], heard: tuple) -> bool:
        """Same number of words, one letter off the heard form (`one_off`), and no known name or term: not the term
        already, nor Markus for `Marcus = Martus` (#1268)."""
        return len(ks) == len(heard) and (a := "".join(ks)) not in self.known and one_off(a, "".join(heard))


def one_off(a: str, b: str) -> bool:
    """`a` is heard form `b` one letter off: `b` 6 letters or more, the same first letter ("i GitHub" is not Git Hub)."""
    return len(b) >= 6 and a[:1] == b[:1] and edits(a, b) == 1


def heard(words: list[dict]) -> str:
    """What the plain decode heard for these words, before any correction."""
    return " ".join(h for w in words if (h := w.get("heard", w["w"])))


def mark(words: list[dict], h: str) -> list[dict]:
    """A corrected span: the first word keeps what was heard, the rest nothing of their own."""
    return [w | {"heard": h if k == 0 else ""} for k, w in enumerate(words)]


def corrections(words: list[dict]) -> list[tuple[str, str]]:
    """`(heard, term)` for each corrected span in `words`."""
    out = []
    for i, w in enumerate(words):
        if w.get("heard"):
            n = next((k for k in range(i + 1, len(words)) if words[k].get("heard") != ""), len(words))
            out.append((w["heard"], " ".join(x["w"] for x in words[i:n])))
    return out


def edits(a: str, b: str) -> int:
    """Levenshtein distance."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


_cache: tuple = (None, None)


def load() -> Vocab | None:
    """The vocabulary from areas.json and people.json, reread when they change. None without a config."""
    global _cache
    try:
        files = [areas.path(), people.path()]
        stamp = tuple((f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else None for f in files)
        if stamp != _cache[0]:
            _cache = (stamp, _read(*files))
    except (OSError, ValueError, KeyError, TypeError):  # a broken config must not stop dictation
        traceback.print_exc(file=sys.stderr)
        _cache = (None, None)
    return _cache[1]


def entries(cfg: dict, ps: list[dict]) -> list[str]:
    """People's names and short names, area names (not the fallback's) and every `vocabulary` entry."""
    return _names(ps) + (cfg.get("vocabulary") or []) + [x for a in cfg.get("areas", []) for x in _area(a)]


def for_area(cfg: dict, area_id: str, ps: list[dict]) -> Vocab | None:
    """A meeting's vocabulary (#429): the area's people (me and `all_areas` included), its name (not the fallback's),
    its `vocabulary` and the root's."""
    members = people.area_members(cfg, area_id, ps)
    es = _names([p for p in ps if p["id"] in members]) + (cfg.get("vocabulary") or []) + _area(areas.get(cfg, area_id))
    return Vocab(es, meeting=True) if es else None


def _names(ps: list[dict]) -> list[str]:
    return [x for p in ps for x in (p.get("name"), p.get("short")) if x]


def _area(a: dict) -> list[str]:
    """The area's name (not the fallback's) and its `vocabulary`."""
    return ([a["name"]] if a.get("id") != areas.DEFAULT and a.get("name") else []) + (a.get("vocabulary") or [])


def _read(areas_json: Path, people_json: Path) -> Vocab | None:
    ps = read_json(people_json, "people")["people"] if people_json.exists() else []
    es = entries(read_json(areas_json, "areas") if areas_json.exists() else {}, ps)
    return Vocab(es) if es else None
