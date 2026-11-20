"""byggmote run: probe, extract, ASR per track, diarize split tracks, merge, write. JSON lines on stdout."""
import gc
import json
import re
import signal
import sys
import tempfile
import time
import traceback
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import WINDOWS, ArgError, __version__, areas, context, media, meeting, merge, models, people, probe, short_error, voice

ROLE = re.compile(r"^(\d+)(?:\.(\d+))?=(.+)$")


class Emitter:
    def __init__(self, out):
        self.out, self.last = out, {}

    def __call__(self, ev: dict):
        if ev["event"] in ("progress", "download"):  # throttle
            k, t = (ev["event"], ev.get("step") or ev.get("model")), time.monotonic()
            if t - self.last.get(k, 0) < 0.5 and ev.get("fraction", 0) < 1 and ("done" not in ev or ev["done"] != ev.get("total")):
                return
            self.last[k] = t
        self.out.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.out.flush()


def units(info: dict, specs: list[str]) -> list[dict]:
    """Active processing units (a track, or a channel of a track) with roles."""
    tracks = {t["id"]: t for t in info["tracks"]}
    roles, chans = dict(info["suggested"]), {}
    for spec in specs:
        m = ROLE.match(spec)
        if not m:
            raise ArgError(f"--track expects N=ROLE or N.K=ROLE: {spec}")
        tid, ch, role = m[1], m[2], m[3].strip()
        if role.lower() in ("skip", "split"):
            role = role.lower()
        if tid in info.get("unreadable", ()):
            continue  # a meeting from before #1405 has the track in meeting.json, so Try Again names it
        if tid not in tracks:
            raise ArgError(f"no track {tid} (file has {len(tracks)})")
        if ch:
            n = tracks[tid]["channels"]
            if not 1 <= int(ch) <= n:
                raise ArgError(f"track {tid} has {n} channel{'s' if n != 1 else ''}")
            chans.setdefault(tid, {})[str(int(ch))] = role
        else:
            roles[tid] = role
    out = []
    for tid, t in tracks.items():
        if tid in chans:
            for k in range(1, t["channels"] + 1):
                out.append({"id": f"{tid}.{k}", "track": int(tid) - 1, "channel": k - 1,
                            "name": t["name"], "role": chans[tid].get(str(k), "split")})
        else:
            out.append({"id": tid, "track": int(tid) - 1, "channel": None, "name": t["name"], "role": roles[tid]})
    if not any(u["role"] != "skip" for u in out):
        raise ArgError("all tracks skipped")
    return out


def speakers_range(s: str | None) -> tuple[int | None, int | None]:
    if not s:
        return None, None
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", s)
    if not m:
        raise ArgError(f"--speakers expects MIN-MAX or N: {s}")
    lo, hi = int(m[1]), int(m[2] or m[1])
    if not 1 <= lo <= hi:
        raise ArgError(f"bad speaker range: {s}")
    return lo, hi


WAVS = 0.05  # the extract step's share for the tracks' wav files; audio.m4a has the rest, so time left comes from the encoding
TITLE_BYTES = 150  # folder names are limited to 255 bytes; å in decomposed form is 3


def _size(s: str) -> int:
    return len(unicodedata.normalize("NFD", s).encode())


# Windows also refuses these in a name, and drops a trailing dot or space (the folder would not be found again).
# A reserved name (CON, NUL…) can't occur: the folder name starts with the date.
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]' if WINDOWS else r"[/:]")


def folder_title(title: str) -> str:
    t = UNSAFE.sub("-", title)
    if _size(t) > TITLE_BYTES:
        t = t[:TITLE_BYTES]
        while _size(t) > TITLE_BYTES - 3:
            t = t[:-1]
        t = t.rstrip() + "…"
    return (t.rstrip(". ") or "-") if WINDOWS else t if t not in (".", "..") else "-"  # "." and ".." name the folder or the one above


def out_dir(area: dict, recorded_at: str, title: str) -> Path:
    stamp = datetime.fromisoformat(recorded_at).strftime("%Y-%m-%d %H%M")
    return meeting.free_dir(areas.transcripts(area) / f"{stamp} {folder_title(title)}")



def language(text: str) -> str | None:
    """sv or en from common function words, None when too little text to tell."""
    ws = [w.strip(".,!?;:\"'()").lower() for w in text.split()]
    sv, en = sum(w in context.SV for w in ws), sum(w in context.EN for w in ws)
    if sv + en < 8:
        return None
    return "sv" if sv > 2 * en else "en" if en > 2 * sv else None


def warnings(m: dict, active: list[dict], words: dict, lang: str) -> list[dict]:
    """No speech at all, or on a track; text that reads as the other language."""
    if not m["segments"]:
        return [{"code": "no-speech"}]
    out = [{"code": "no-speech", "track": u["id"]} for u in active if not words[u["id"]]]
    heard = language(" ".join(g["text"] for g in m["segments"]))
    if heard and heard != lang:
        out.append({"code": "language", "lang": heard})
    return out


# Windows has no SIGTERM from outside: the app sends CTRL_BREAK_EVENT (SIGBREAK) or ends the process.
SIGNALS = (signal.SIGINT, signal.SIGTERM) + ((signal.SIGBREAK,) if WINDOWS else ())


class Stopped(BaseException):
    """SIGTERM, SIGINT or SIGBREAK. Not an Exception, so the model libraries' `except Exception` can't swallow it."""


def _hold():
    """Ignore further stop signals so the cleanup can finish."""
    for s in SIGNALS:
        signal.signal(s, signal.SIG_IGN)


stopping = None  # "stopped (SIGTERM)" once a stop signal came


def _stop(sig, _frame):
    global stopping
    _hold()
    stopping = f"stopped ({signal.Signals(sig).name})"
    raise Stopped(stopping)


@contextmanager
def on_stop(handler=_stop):
    """The stop signals go to `handler`. The default raises Stopped, so every `with` and `finally` cleans up."""
    prev = {s: signal.signal(s, handler) for s in SIGNALS}
    try:
        yield
    finally:
        for s, h in prev.items():
            signal.signal(s, h)


def mix_tracks(info: dict, us: list[dict]) -> list[int]:
    if info["source"] == "obs" and [t["id"] for t in info["tracks"]] == ["1", "2", "3"]:
        return [0]
    return sorted({u["track"] for u in us if u["role"] != "skip"})


def attendee(text: str) -> dict:
    """`Anna Andersson <anna@x.se>`, `Anna Andersson` or `<anna@x.se>` → {name, email}; no name is the email."""
    hit = re.fullmatch(r"(.*?)\s*<([^<>\s]+@[^<>\s]+)>", text.strip())
    name, email = (hit[1], hit[2]) if hit else (text, None)
    name = " ".join(name.split()) or email
    if not name:
        raise ArgError(f"--attendee: empty: {text!r}")
    return {"name": name, "email": email}


def vocab_for(cfg: dict, area_id: str, ps: list[dict]):
    """The area's vocabulary; a broken entry gives the plain decode, never a failed meeting."""
    try:
        return context.for_area(cfg, area_id, ps)
    except (ValueError, KeyError, TypeError, AttributeError):
        traceback.print_exc(file=sys.stderr)
        return None


def run(a) -> int:
    out, sys.stdout = sys.stdout, sys.stderr  # model libraries print; keep stdout for events
    emit = Emitter(out)
    t_run = time.time()
    d, m, step = None, None, "config"
    try:
        cfg = areas.load()
        area = areas.get(cfg, a.area)
        ps = people.load()
        step = "probe"
        info = probe.probe(Path(a.file), cfg.get("me"))
        step = "args"
        us = units(info, a.track or [])
        for u in us:
            if u["role"] not in ("skip", "split"):
                p = people.resolve(u["role"], cfg, area["id"], ps)
                u["person"], u["label"] = (p["id"], people.label(p)) if p else (None, u["role"])
        lo, hi = speakers_range(a.speakers)
        invited = [attendee(x) for x in a.attendee]
        lang = a.lang or area.get("lang", "sv")
        title = " ".join((a.title or info["title"] or "").split()) or meeting.LABELS.get(lang, meeting.LABELS["en"])[0]
        step = "write"
        d = meeting.free_dir(Path(a.out).expanduser()) if a.out else out_dir(area, info["recorded_at"], title)
        d.mkdir(parents=True, exist_ok=True)
        active = [u for u in us if u["role"] != "skip"]
        split = [u for u in active if u["role"] == "split"]
        steps = (["extract"] + [f"asr:{u['id']}" for u in active] + [f"diarize:{u['id']}" for u in split]
                 + ["merge", "write"])
        emit({"event": "start", "dir": str(d), "steps": steps})

        m = {"schema": meeting.SCHEMA, "title": title, "area": area["id"], "lang": lang, "status": "processing",
             "recorded_at": info["recorded_at"], "duration": info["duration"], "created_at": meeting.now(),
             "updated_at": meeting.now(),
             "source": {"path": info["path"], "size": info["size"], "kind": info["source"]},
             "tracks": [{"id": u["id"], "name": u["name"]} | (
                 {"role": "skip"} if u["role"] == "skip" else
                 {"role": "split", "speakers": {"min": lo, "max": hi}} if u["role"] == "split" else
                 {"role": "person", "person": u["person"]}) for u in us],
             "attendees": invited, "speakers": [], "segments": [], "engine": {"version": __version__, "steps": []}}
        meeting.save(d, m, transcript=False)

        def timed(name: str, fn, record: str | None = None, **extra):
            """Each step's time goes to meeting.json under `record` or its name, so the app learns how long a run takes (FEATURES.md,
            Processing). `write`'s comes after the file is saved."""
            nonlocal step
            step = name
            emit({"event": "step", "step": name, "status": "start"})
            t0, top = time.time(), 0.0

            def progress(f: float):  # adapters can overshoot or restart a phase; the app gets 0–1, never back
                nonlocal top
                top = max(top, min(f, 1.0))
                emit({"event": "progress", "step": name, "fraction": round(top, 3)})

            r = fn(progress)
            sec = round(time.time() - t0, 1)
            emit({"event": "step", "step": name, "status": "done", "seconds": sec})
            m["engine"]["steps"].append({"step": record or name} | extra | {"seconds": sec})
            return r

        def load(e: dict):
            models.ensure(e, emit)
            x = models.adapter(e)
            x.load(models.device() if e["type"] == "diarize" else models.ASR_DEVICE)
            return x

        import soundfile as sf
        with tempfile.TemporaryDirectory(prefix="byggmote-") as tmp:
            def extract(progress):
                # The tracks' wav files take a twentieth of the step, audio.m4a the rest: on an hour's file the AAC encoding takes about 9 s
                # of 9.5, and the step stood at 50 % meanwhile (#1400).
                wavs = {}
                for i, u in enumerate(active):
                    p = Path(tmp) / f"{u['id']}.wav"
                    media.extract_wav(Path(info["path"]), u["track"], u["channel"], p)
                    wavs[u["id"]] = sf.read(p, dtype="float32")[0]
                    progress(WAVS * (i + 1) / len(active))
                media.extract_mix(Path(info["path"]), mix_tracks(info, us), d / "audio.m4a",
                                  lambda f: progress(WAVS + (1 - WAVS) * f), info["duration"])
                return wavs
            audio = timed("extract", extract)
            if not m["duration"]:  # a recording cut while it grew (a browser's WebM) names no length: the decoded sound has it
                m["duration"] = info["duration"] = round(max(len(a) for a in audio.values()) / media.SR, 2)

            asr_e = models.default("asr", lang)
            asr = timed("load", lambda _: load(asr_e), "load:asr")
            vocab = None if a.no_vocabulary else vocab_for(cfg, area["id"], ps)
            words = {}
            for u in active:
                words[u["id"]] = timed(f"asr:{u['id']}", lambda p, u=u: asr.words(audio[u["id"]], p, vocab),
                                       adapter=asr_e["id"], model=asr_e["model"], device=models.ASR_DEVICE)
            del asr
            gc.collect()  # collect before the GPU caches can give the memory back
            models.free_gpu()

            # A split track with no words has no speakers to find: on an hour of silent Others that saves ~20 s, and the speaker
            # model's load when no track needs it. The app learns the shorter plan, so its deck keeps pace (#1158).
            quiet = {u["id"] for u in split if not words[u["id"]]}
            if quiet:
                steps = [s for s in steps if not (s.startswith("diarize:") and s.removeprefix("diarize:") in quiet)]
                emit({"event": "steps", "steps": steps})
                m["engine"]["steps"] += [{"step": f"diarize:{uid}", "seconds": 0.0} for uid in quiet]  # so the app learns it is often skipped
            dia, dia_model, no_speakers = {uid: ([], {}) for uid in quiet}, None, None
            if loud := [u for u in split if u["id"] not in quiet]:
                try:
                    dia_e = models.default("diarize")
                    dia_model = dia_e.get("prints", dia_e["model"])  # what voice prints are tagged with
                    dz = timed("load", lambda _: load(dia_e), "load:diarize")
                except Exception as e:  # no speaker model: keep the words, each split track is one speaker
                    if stopping:
                        raise
                    traceback.print_exc(file=sys.stderr)
                    no_speakers = short_error(e)
                    dia |= {u["id"]: ([], {}) for u in loud}
                else:
                    for u in loud:
                        name = f"diarize:{u['id']}"
                        dia[u["id"]] = timed(name, lambda p, u=u: dz.diarize(audio[u["id"]], lo, hi, p),
                                             adapter=dia_e["id"], model=dia_model,
                                             device=models.device())
                        m["engine"]["steps"][-1]["found"] = len({t[2] for t in dia[u["id"]][0]})

        def merged(_):
            by_name = {(u["name"] or "").lower(): u["id"] for u in active if u["channel"] is None}
            if {"mic", "others"} <= by_name.keys():  # a call: speakers echo into Mic (#712, #1220)
                mic, others = by_name["mic"], by_name["others"]
                voices = merge.assign(words[mic], dia[mic][0]) if mic in dia else None
                words[mic] = merge.without_echo(words[mic], words[others], voices)
                if mic in dia:
                    turns, prints = dia.get(others, ([], {}))
                    words[mic] = merge.without_leftovers(words[mic], merge.assign(words[mic], dia[mic][0]), words[others],
                                                         merge.assign(words[others], turns), dia[mic][1], prints, voice.SAME_ACROSS_TRACKS.get(dia_model))
            for uid in dia:  # after the call's leftovers went, so none joins the user's voice
                turns, prints = dia[uid]
                dia[uid] = models.fold(turns, lambda kt: prints.get(kt[0][2]), len(audio[uid]) / models.SR, keep=lo or 1, cap=hi), prints
            tagged = []
            for u in active:
                ws = words[u["id"]]
                if u["role"] == "split":
                    labels = merge.assign(ws, dia[u["id"]][0])
                    tagged += [w | {"speaker": (u["id"], lab or "?")} for w, lab in zip(ws, labels)]
                else:
                    tagged += [w | {"speaker": (u["id"], None)} for w in ws]
            first = {}
            for w in sorted(tagged, key=lambda w: w["s"]):
                first.setdefault(w["speaker"], len(first))
            byid = {u["id"]: u for u in active}
            sid, auto = {}, 0
            for key in first:
                uid, cluster = key
                sid[key] = f"S{len(sid) + 1}"
                pid = None
                if cluster is None:
                    name, pid, emb = byid[uid]["label"], byid[uid]["person"], None
                else:
                    auto += 1
                    name = f"{meeting.UNNAMED}{auto}"
                    vec = dia[uid][1].get(cluster) if voice.on(cfg) else None
                    emb = {"model": dia_model, "vector": vec} if vec else None
                m["speakers"].append({"id": sid[key], "name": name, "person": pid, "track": uid, "cluster": cluster, "embedding": emb})
            for w in tagged:
                w["speaker"] = sid[w["speaker"]]
            m["segments"] = merge.segments(tagged)
            if any(s["embedding"] for s in m["speakers"]):
                try:  # a suggestion only: never fails the run
                    voice.recognise(m, cfg, ps, voice.prints(cfg, dia_model, skip=d))
                except Exception:
                    traceback.print_exc(file=sys.stderr)

        heard = dict(words)  # before the echo rules: a Mic that held only the call did hear speech
        timed("merge", merged)
        m["status"], m["warnings"] = "review", warnings(m, active, heard, lang)
        if no_speakers is not None:
            m["warnings"].append({"code": "no-speakers", "message": no_speakers})
        timed("write", lambda _: meeting.save(d, m))
        emit({"event": "done", "dir": str(d), "seconds": round(time.time() - t_run, 1),
              "speakers": len(m["speakers"]), "segments": len(m["segments"]), "warnings": m["warnings"]})
        return 0
    except (Exception, Stopped) as e:
        _hold()
        if not isinstance(e, (Stopped, ArgError)):
            traceback.print_exc(file=sys.stderr)
        msg = stopping or short_error(e)  # a model library can turn Stopped into an error of its own
        try:
            if m:
                m["status"], m["error"] = "failed", f"{step}: {msg}"
                meeting.save(d, m, transcript=False)
        except OSError:
            pass  # the folder is gone or read-only; the error event still tells the app
        try:
            emit({"event": "error", "step": step, "message": msg})
        except OSError:
            pass
        return 2 if isinstance(e, ArgError) else 1
    finally:
        sys.stdout = out
