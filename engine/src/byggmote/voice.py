"""Who an unnamed speaker is from their voice: their embedding against the named speakers' in every other meeting (#485).
Recognise Voices can be off, and a person's voice prints can be forgotten, because a voice print is biometric data (#1137)."""
import math
from pathlib import Path

from . import areas, knowledge, meeting, people
from .models import CAMPPLUS

# Cosine similarity per embedding model. pyannote community-1, measured on Tim's meetings 2026-10-01 (#485): the same
# person in another meeting scored at least 0.63 at best, two different people at most 0.51 (both with 10 s of speech or
# more). CAM++ (Windows), measured on the AMI meetings ES2002b and c (#794): the same person at least 0.68 with 10 s,
# 0.79 with 60 s; two different people at most 0.33.
THRESHOLDS = {"pyannote/speaker-diarization-community-1": 0.6, CAMPPLUS: 0.5}
# The best person must score this much above the next one, because two people often score almost the same (0.97 and 0.97).
# Replayed on Tim's 92 meetings with every voice unnamed (2026-11-18, #1463): wrong matches 25 without it, 2 with it; right 272 and 261.
LEAD = 0.1
# Less speech than this gives an embedding that matches anyone (an 8 s fragment: 0.04 against the same person, 0.61 against another).
MIN_SECONDS = 10.0
# A Mic voice against an Others voice in the same meeting, per embedding model. pyannote community-1, measured on Tim's 18 calls
# with Mic split 2026-11-03 (#1335): people at the mic scored at most 0.49, and the call heard on Mic mostly 0.62 to 0.97. Not
# CAM++: sherpa-onnx's diarization can hear the user and the call as one voice (#1245), and that voice must not go.
SAME_ACROSS_TRACKS = {"pyannote/speaker-diarization-community-1": 0.6}


def unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _speech(m: dict) -> dict[str, float]:
    out = {}
    for g in m["segments"]:
        out[g["speaker"]] = out.get(g["speaker"], 0.0) + g["end"] - g["start"]
    return out


def prints(cfg: dict, model: str, skip: Path | None = None) -> list[tuple[str, list[float]]]:
    """(person, unit vector) for every linked speaker with enough speech, in every meeting but `skip`."""
    out = []
    for d, m in meeting.everywhere(cfg):
        if skip and d.resolve() == skip.resolve():
            continue
        talk = _speech(m)
        for s in m["speakers"]:
            e = s.get("embedding")
            if s.get("person") and e and e.get("model") == model and talk.get(s["id"], 0) >= MIN_SECONDS:
                out.append((s["person"], unit(e["vector"])))
    return out


def recognise(m: dict, cfg: dict, ps: list[dict], known: list[tuple[str, list[float]]]):
    """`voice: {person, score}` on each unnamed speaker whose best match is above its model's threshold and LEAD above the next
    person: the area's people first, then anyone. Not someone already in the meeting: picking them would merge the two speakers."""
    present = {x.get("person") for x in m["speakers"] + m.get("tracks", [])}
    exists = {p["id"] for p in ps} - present
    members = people.area_members(cfg, m["area"], ps)
    talk = _speech(m)
    for s in m["speakers"]:
        e = s.get("embedding")
        if s.get("person") or not e or not s["name"].startswith(meeting.UNNAMED) or talk.get(s["id"], 0) < MIN_SECONDS:
            continue
        v, best = unit(e["vector"]), {}
        for pid, u in known:
            if pid in exists:
                best[pid] = max(best.get(pid, -1.0), sum(a * b for a, b in zip(v, u)))
        for group in ({p: x for p, x in best.items() if p in members}, best):
            pid = max(group, key=group.get, default=None)
            runner_up = max((x for p, x in group.items() if p != pid), default=-1.0)
            if pid and group[pid] >= THRESHOLDS[e["model"]] and group[pid] - runner_up >= LEAD:
                s["voice"] = {"person": pid, "score": round(group[pid], 3)}
                break


def on(cfg: dict) -> bool:
    """Recognise Voices: `"voices": false` in areas.json, as a new areas.json has it, is off. Missing is on: `voices on` removes the key,
    and a knowledge base from before #1333 has none and stays on."""
    return cfg.get("voices", True) is not False


def turn(value: bool) -> dict:
    """`byggmote voices on|off`. Off keeps no new voice prints and recognises no one; prints already kept stay until forgotten."""
    with knowledge.locked(knowledge.folder()):
        cfg = areas.load()
        if value:
            cfg.pop("voices", None)
        else:
            cfg["voices"] = False
        areas.save(cfg)
    return {"voices": value}


def forget(pid: str) -> list[str]:
    """`byggmote people forget-voice ID`: the person's voice prints and the voice matches to them leave every meeting. Names stay.
    Returns the rewritten meetings."""
    with knowledge.locked(knowledge.folder()):
        cfg, ps = areas.load(), people.load()
        p = people._get(ps, pid)
        done = []
        for d, m in meeting.everywhere(cfg):
            hit = False
            for s in m["speakers"]:
                if s.get("person") == p["id"] and s.get("embedding"):
                    s["embedding"], hit = None, True
                if (s.get("voice") or {}).get("person") == p["id"]:
                    del s["voice"]
                    hit = True
            if hit:
                meeting.save(d, m, transcript=False)
                done.append(str(d))
        return done
