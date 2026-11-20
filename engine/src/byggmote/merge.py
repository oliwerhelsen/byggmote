"""Words (with speaker keys) to segments; diarization turns to per-word speakers."""
from bisect import bisect_left, bisect_right
from collections import Counter
from itertools import accumulate

from .context import key
from .voice import unit

PAUSE = 2.0
LONG = 20.0  # a line this long ends at the next sentence end
MAX = 60.0  # and at this length regardless
ECHO = 1.0  # s; echo reaches Mic up to this long after the same word on Others: speaker playback, then the room (#712)
SLACK = 0.2  # s; and ASR may time the echo this much earlier than the original
CALL = 0.5  # a Mic voice with more than this share of echo words is the call itself (#1220)
CALL_WORDS = 5  # and at least this many: a short "ja" back to Others is not the call
CALL_DELAY = 0.5  # s; such a voice's words starting this long after an Others word starts are its echo, heard or not: the speakers'
# delay. Shorter than ECHO, which allows for ASR timing a repeated word late, so a reply right after Others stops stays (#1245)
NEAR = 2.0  # s; a Mic word this close to an Others word is in the call's time, for its leftovers (#1335)


def assign(words: list[dict], turns: list[tuple[float, float, str]]) -> list[str | None]:
    """Speaker per word by max overlap with the turns; nearest turn if none overlaps. Turns may overlap (sherpa-onnx's
    do, pyannote's exclusive ones don't): the scan goes back while any earlier turn still reaches the word, and an
    equal overlap goes to the later turn, usually the short interjection."""
    if not turns:
        return [None] * len(words)
    turns = sorted(turns)
    starts, reach = [t[0] for t in turns], list(accumulate((t[1] for t in turns), max))
    out = []
    for w in words:
        i = bisect_right(starts, w["e"])
        best, ov = None, 0.0
        j = i - 1
        while j >= 0 and reach[j] > w["s"]:
            o = min(turns[j][1], w["e"]) - max(turns[j][0], w["s"])
            if o > ov or (best is None and o == 0 and turns[j][0] <= w["s"] and w["e"] <= turns[j][1]):  # a word of no length inside
                best, ov = turns[j][2], o
            j -= 1
        if best is None:
            mid = (w["s"] + w["e"]) / 2
            near = [turns[k] for k in (i - 1, i) if 0 <= k < len(turns)]
            best = min(near, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]
        out.append(best)
    return out


def without_echo(mic: list[dict], others: list[dict], voices: list[str | None] | None = None) -> list[dict]:
    """Mic words without the call's echo: a word that repeats an Others word starting from ECHO s before it to
    SLACK s after its start (echo is never earlier). Each Others word takes at most one Mic word. With `voices` (the
    Mic speaker per word): a voice with at least CALL_WORDS and more than CALL of its words echoed is the call in the speakers, and its
    words in the call's time go, also the ones ASR heard differently on the two tracks ("Marcus", "Markus"). Its words while Others is
    quiet stay: they are the user's, when diarization heard the user and the echo as one voice (sherpa-onnx's, Windows and Linux,
    #1245)."""
    others = sorted(others, key=lambda w: w["s"])
    starts, used, echoed = [o["s"] for o in others], set(), []
    # The call's time: where an echo of an Others word can start, from SLACK s before its start to CALL_DELAY s after it, merged.
    spans: list[list[float]] = []
    for o in others:
        a, b = o["s"] - SLACK, o["s"] + CALL_DELAY
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    span_starts = [s[0] for s in spans]

    def in_call(w: dict) -> bool:
        i = bisect_right(span_starts, w["s"]) - 1
        return i >= 0 and w["s"] <= spans[i][1]

    for w in mic:
        k, hit = key(w["w"]), False
        for j in range(bisect_left(starts, w["s"] - ECHO), bisect_right(starts, w["s"] + SLACK)):
            if k and j not in used and key(others[j]["w"]) == k:
                used.add(j)
                hit = True
                break
        echoed.append(hit)
    if voices:
        hits = {v: sum(e for e, u in zip(echoed, voices) if u == v) for v in set(voices) if v is not None}
        call = {v for v, n in hits.items() if n >= CALL_WORDS and n > CALL * voices.count(v)}
        echoed = [e or (v in call and in_call(w)) for e, v, w in zip(echoed, voices, mic)]
    return [w for w, e in zip(mic, echoed) if not e]


def without_leftovers(mic: list[dict], voices: list[str | None], others: list[dict], other_voices: list[str | None],
                      prints: dict[str, list[float]], other_prints: dict[str, list[float]], same: float | None) -> list[dict]:
    """What without_echo leaves of the call on Mic goes (#1335). `voices` are the Mic speaker per word in `mic`, `other_voices` the
    Others speaker per word in `others`. Only a voice with more than half of its words within NEAR s of an Others word can go, so
    a person at the mic who speaks while Others is quiet stays. It goes when its print scores at least `same` against an Others
    voice with more words (the more words: a fragment of the user on Others must not take the user's voice), or when it is under
    CALL_WORDS and not the largest."""
    if not mic or not others:
        return mic
    starts = sorted(o["s"] for o in others)

    def near(w: dict) -> bool:
        i = bisect_left(starts, w["s"])
        return any(abs(starts[k] - w["s"]) < NEAR for k in (i - 1, i) if 0 <= k < len(starts))

    count, other_count = Counter(voices), Counter(other_voices)
    close = Counter(v for w, v in zip(mic, voices) if near(w))
    largest = count.most_common(1)[0][0]

    def heard_again(v) -> bool:
        if same is None or v not in prints:
            return False
        u = unit(prints[v])
        return any(count[v] < other_count[o] and sum(a * b for a, b in zip(u, unit(p))) >= same for o, p in other_prints.items())

    gone = {v for v in count if close[v] * 2 > count[v] and (heard_again(v) or v != largest and count[v] < CALL_WORDS)}
    return [w for w, v in zip(mic, voices) if v not in gone]


def _full(seg: dict, at: float) -> bool:
    long = at - seg["start"]
    return long > MAX or long > LONG and seg["words"][-1]["w"].endswith((".", "?", "!"))


def segments(words: list[dict]) -> list[dict]:
    """words: {w, s, e, heard?, speaker}, any order. New segment on speaker change, pause > PAUSE or a long line (LONG, MAX)."""
    segs = []
    for w in sorted(words, key=lambda w: w["s"]):
        cur = segs[-1] if segs else None
        if not cur or cur["speaker"] != w["speaker"] or w["s"] - cur["end"] > PAUSE or _full(cur, w["s"]):
            cur = {"id": len(segs) + 1, "start": w["s"], "end": w["e"], "speaker": w["speaker"], "words": []}
            segs.append(cur)
        cur["words"].append({k: w[k] for k in ("w", "s", "e", "heard") if k in w})
        cur["end"] = max(cur["end"], w["e"])
    for s in segs:
        s["text"] = " ".join(w["w"] for w in s["words"])
    return [{k: s[k] for k in ("id", "start", "end", "speaker", "text", "words")} for s in segs]
