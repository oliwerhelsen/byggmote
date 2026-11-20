"""byggmote serve: resident engine. ASR models stay loaded; one JSON request per stdin line, one JSON event per stdout line.

Requests are handled in order. Languages in --langs are preloaded in the background while no request waits;
a request for a language not loaded yet loads it first.
"""
import json
import os
import queue
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__, context, fillers, media, models, scratch, short_error
from .run import Emitter, on_stop


def read_audio(path: Path):
    import soundfile as sf
    try:
        a, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr == media.SR and a.shape[1] == 1:
            return a[:, 0]
    except sf.LibsndfileError:
        pass  # a recording cut short by a crash has a header libsndfile rejects; ffmpeg reads it
    import tempfile
    with tempfile.TemporaryDirectory(prefix="byggmote-") as tmp:
        wav = Path(tmp) / "a.wav"
        media.extract_wav(path, 0, None, wav)
        return sf.read(wav, dtype="float32")[0]


def normalize(a, peak: float = 0.9, max_gain: float = 60.0):
    """Quiet microphones (low input volume) give near-silent audio the model reads as nothing. Scale up to `peak`."""
    import numpy as np
    top = float(np.abs(a).max()) if len(a) else 0.0
    return a if top <= 0 else a * min(max_gain, peak / top) if top < peak else a


def read_growing(path: Path):
    """The PCM the app has written so far into a dictation's WAV (16 kHz mono 16-bit, a 44-byte header that says 0 bytes
    until stop); whole samples only, as a write can be half done. The same samples soundfile reads at stop."""
    import numpy as np
    b = path.read_bytes()[44:]
    return np.frombuffer(b[: len(b) & ~1], dtype="<i2").astype("float32") / 32768


class Stream:
    """A long dictation transcribed while the user speaks (#1285, measured in #343: `pause-30/0.3/10/2`). The recording
    is cut at the quietest 0.1 s within 30 s ± 30 % of the last cut, and each chunk is transcribed once its audio and
    2 s more are in, from 10 s before the cut, as dictation transcribes a clip; the words in the context are dropped.
    At stop only the rest is left. A dictation with no cut (under about 39 s) is transcribed whole after stop, as before."""
    CHUNK, WINDOW, LEFT, RIGHT = 30 * media.SR, 9 * media.SR, 10 * media.SR, 2 * media.SR

    def __init__(self, path: Path, lang: str, ctx: bool):
        self.path, self.lang, self.ctx = path, lang, ctx
        self.cuts, self.words, self.fixes = [0], [], []

    def same(self, path: Path, lang: str, ctx: bool) -> bool:
        return (self.path, self.lang, self.ctx) == (path, lang, ctx)

    def run(self, a, audio, vocab, stop: bool = False):
        """Transcribes the chunks whose audio is in: at `stop`, every one left. Returns False when the cuts differ from
        the ones already transcribed (other audio): nothing is kept then."""
        b = a.cuts(audio, self.CHUNK, self.WINDOW)
        if b[:len(self.cuts)] != self.cuts:
            return False
        end = len(audio)
        for lo, hi in zip(b[len(self.cuts) - 1:], b[len(self.cuts):]):
            if not stop and (hi == end or hi + self.RIGHT > end):
                break
            s0, s1, last = max(0, lo - self.LEFT), min(end, hi + self.RIGHT), hi == end
            if s1 - s0 >= media.SR // 10:  # the log-mel needs a few frames
                words, fixes = a.span(normalize(audio[s0:s1]), s0 / media.SR, lo / media.SR,
                                      None if last else hi / media.SR, vocab)
                self.words += words
                self.fixes += fixes
            if not last:
                self.cuts.append(hi)
        return True

    def next_cut(self) -> int:
        """How many samples the recording needs before another cut can be made."""
        return self.cuts[-1] + self.CHUNK + self.WINDOW + 1


class Server:
    def __init__(self, langs: list[str], emit):
        self.emit, self.pending, self.asr = emit, list(dict.fromkeys(l for l in langs if l)), {}
        self.dev = models.ASR_DEVICE
        self.stream: Stream | None = None  # the dictation being recorded, transcribed as it grows (`listen`)

    def load(self, lang: str):
        e = models.default("asr", lang)
        models.ensure(e, self.emit)
        t0 = time.time()
        a = models.adapter(e)
        a.load(self.dev)
        import numpy as np
        a.words(np.zeros(media.SR, dtype="float32"), lambda f: None)  # first call compiles the GPU kernels
        models.free_gpu()
        self.asr[lang] = (e, a)
        if lang in self.pending:
            self.pending.remove(lang)
        self.emit({"event": "loaded", "lang": lang, "model": e["model"], "seconds": round(time.time() - t0, 1)})
        if not self.pending:
            self.emit({"event": "ready", "langs": sorted(self.asr), "device": self.dev, "version": __version__})

    def handle(self, req: dict):
        rid, op = req.get("id"), req.get("op")
        if op == "ping":
            return {"id": rid, "event": "pong", "langs": sorted(self.asr), "pending": self.pending}
        if op not in ("transcribe", "warm", "listen"):
            raise ValueError(f"unknown op: {op!r}")
        lang = req.get("lang") or "sv"
        if lang not in self.asr:
            self.load(lang)
        e, a = self.asr[lang]
        if op == "warm":  # sent when recording starts: the GPU idles down between dictations, ~2 s to wake
            import numpy as np
            t0 = time.time()
            a.words(np.zeros(media.SR // 2, dtype="float32"), lambda f: None)
            return {"id": rid, "event": "warm", "lang": lang, "seconds": round(time.time() - t0, 3)}
        path, ctx = Path(req["audio"]).expanduser(), bool(req.get("context"))
        if op == "listen":
            return self.listen(a, path, lang, ctx)
        t0 = time.time()
        raw = read_audio(path)
        s, self.stream = self.stream, None
        chunked = s is not None and s.same(path, lang, ctx) and len(s.cuts) > 1  # a chunk was done while recording
        vocab = context.load() if ctx else None
        if chunked and s.run(a, raw, vocab, stop=True):
            heard, fixes = s.words, s.fixes
            if vocab:
                heard, f = vocab.replace(heard)
                fixes = fixes + f
        else:  # a short dictation, one in another language than its chunks (#940), a recovered one: the whole clip, as before
            chunked = False
            heard = a.words(normalize(raw), lambda f: None, vocab)
            fixes = a.fixes
        words = fillers.clean(heard, lang)
        return {"id": rid, "event": "result", "text": " ".join(w["w"] for w in words), "words": words,
                "raw": " ".join(w["w"] for w in heard),
                "lang": lang, "model": e["model"], "audio_seconds": round(len(raw) / media.SR, 2),
                "seconds": round(time.time() - t0, 3)} | ({"fixes": fixes} if ctx else {}) \
            | ({"chunks": len(s.cuts)} if chunked else {})

    def listen(self, a, path: Path, lang: str, ctx: bool):
        """The app records `path`: the chunks whose audio is in are transcribed now. No reply. A dictation in another
        language, or with or without context, starts over, so the language chosen at stop sets the whole text (#940).
        A failure is only logged: stop then transcribes the whole clip."""
        if not (self.stream and self.stream.same(path, lang, ctx)):
            self.stream = Stream(path, lang, ctx)
        s = self.stream
        try:
            if (os.path.getsize(path) - 44) // 2 < s.next_cut():
                return None
            if not s.run(a, read_growing(path), context.load() if ctx else None):
                self.stream = None
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.stream = None
        return None

    def loop(self, q: "queue.Queue"):
        if not self.pending:  # --langs "": nothing downloaded to preload; a request loads (and downloads) its language
            self.emit({"event": "ready", "langs": [], "device": self.dev, "version": __version__})
        while True:
            try:
                line = q.get(block=not self.pending)
            except queue.Empty:
                try:
                    self.load(self.pending[0])
                except Exception as e:
                    traceback.print_exc(file=sys.stderr)
                    self.emit({"event": "error", "message": f"load {self.pending.pop(0)}: {short_error(e)}"})
                    if not self.pending:
                        self.emit({"event": "ready", "langs": sorted(self.asr), "device": self.dev, "version": __version__})
                continue
            if line is None:
                return
            req = {}
            try:
                req = json.loads(line)
                if req.get("op") == "quit":
                    return
                if (out := self.handle(req)) is not None:
                    self.emit(out)
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                self.emit({"id": req.get("id"), "event": "error", "message": short_error(e)})


def serve(a) -> int:
    out, sys.stdout = sys.stdout, sys.stderr  # model libraries print; keep stdout for events
    emit = Emitter(out)
    q: queue.Queue = queue.Queue()

    def reader():
        for line in sys.stdin:
            if line.strip():
                q.put(line)
        q.put(None)  # EOF: the app went away

    threading.Thread(target=reader, daemon=True).start()
    def stop(_sig, _frame):
        # At once, not by exception: model-loading code can turn one into another error and load on.
        shutil.rmtree(tmp, ignore_errors=True)
        os._exit(1)

    with scratch() as tmp, on_stop(stop):
        try:
            emit({"event": "start", "pid": os.getpid(), "version": __version__})
            Server(a.langs.split(","), emit).loop(q)
            return 0
        except Exception as e:  # outside a request: say it in one sentence, the traceback goes to stderr
            traceback.print_exc(file=sys.stderr)
            emit({"event": "error", "message": short_error(e)})
            return 1
        finally:
            sys.stdout = out
