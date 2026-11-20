"""Model registry and adapters. New engine: an adapter class + a REGISTRY row.

ASR adapter:     load(device); words(audio: float32 16 kHz mono, progress) -> [{w, s, e}]
Diarize adapter: load(device); diarize(audio, min, max, progress) -> (turns [(s, e, label)], {label: vector})
LLM adapter:     load(); summarize(prompt) -> text
"""
import errno
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from fnmatch import fnmatch
from pathlib import Path
from typing import NamedTuple

import numpy as np

from . import BACKEND, LOCAL_MODEL, WINDOWS, replace, short_error
from .media import SR

ASR_DEVICE = "mlx" if BACKEND == "mlx" else "cpu"

# Each model is fetched and loaded at a fixed commit of its repo (`revision`, and the third item of `extra`), never at the repo's
# latest: the repos are other people's, and a changed file there must not reach a computer without a change here. A new revision
# is a change to this file, checked like code (#1419).
PARAKEET_MLX = "ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15"

MLX = [
    {"id": "pianissimo", "type": "asr", "name": "Pianissimo", "langs": ["sv"], "model": "KlangAI/pianissimo-sv-mlx-8bit",
     "revision": "7b4d528bfb7ce3c66e2a187904f8d86ac39bc6de",
     "size": 759_344_953, "license": "CC BY 4.0", "default": ["sv"], "adapter": "mlx"},
    {"id": "parakeet-v3", "type": "asr", "name": "Parakeet v3", "langs": ["en"], "model": "mlx-community/parakeet-tdt-0.6b-v3",
     "revision": PARAKEET_MLX,
     "size": 2_508_893_745, "license": "CC BY 4.0", "default": ["en"], "adapter": "mlx"},
    # Gated on Hugging Face (contact form), so Byggmöte.app ships it under the same licence (scripts/vendor.sh).
    {"id": "pyannote-community-1", "type": "diarize", "name": "pyannote community-1", "langs": [], "model": "pyannote/speaker-diarization-community-1",
     "revision": "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee",
     "size": 32_000_000, "license": "CC BY 4.0", "default": ["*"], "adapter": "pyannote"},
    # The minutes on the Mac, chosen over Gemma 4 E4B and 12B by measurement (#569). Never fetched unasked. Only in an edition with the
    # local model (docs/EDITIONS.md, `localModel`).
    *([{"id": "qwen3.5-9b", "type": "llm", "name": "Qwen3.5 9B", "langs": ["sv", "en"], "model": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "revision": "938d8919941c6e7efd3c7150eff7fe9d12afa631",
        "size": 5_977_071_067, "license": "Apache 2.0", "default": [], "min_ram_gb": 16, "adapter": "mlx-lm"}] if LOCAL_MODEL else []),
]
# The CPU only, int8, on Windows and Linux (docs/WINDOWS.md, #792; docs/LINUX.md). `chunk` in seconds keeps an hour-long meeting under 3 GB on the X1 Carbon.
# `extra`: one more file from another repo. Parakeet's ONNX repo has no tokenizer.model, which phrase boosting needs.
CAMPPLUS = "3dspeaker/speech_campplus_sv_zh_en_16k-common_advanced"  # the speaker embedding with ONNX
ONNX = [
    {"id": "pianissimo", "type": "asr", "name": "Pianissimo", "langs": ["sv"], "model": "KlangAI/pianissimo-sv-onnx",
     "revision": "63730c6021234f26b9bbae9a07a04fec39e7a52e",
     "size": 660_794_588, "license": "CC BY 4.0", "default": ["sv"], "adapter": "onnx", "chunk": 120},
    {"id": "parakeet-v3", "type": "asr", "name": "Parakeet v3", "langs": ["en"], "model": "istupakov/parakeet-tdt-0.6b-v3-onnx",
     "revision": "8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce",
     "size": 670_840_955, "license": "CC BY 4.0", "default": ["en"], "adapter": "onnx", "chunk": 30,
     "extra": ("mlx-community/parakeet-tdt-0.6b-v3", "tokenizer.model", PARAKEET_MLX)},
    # pyannote segmentation-3.0 (MIT) and 3D-Speaker's CAM++ (Apache 2.0) through sherpa-onnx. `prints` names the
    # embedding, which voice prints are tagged with: never compared with community-1's.
    {"id": "campplus", "type": "diarize", "name": "segmentation-3.0 + CAM++", "langs": [],
     "model": "csukuangfj/speaker-embedding-models", "revision": "0743f301363dec56491a490f6d6cbc9d67f9a3bf",
     "size": 29_821_670, "license": "MIT, Apache 2.0", "default": ["*"],
     "adapter": "sherpa", "extra": ("csukuangfj/sherpa-onnx-pyannote-segmentation-3-0", "model.int8.onnx", "9403a6902bb58e3d5ae8c7e77c3422de279db2e0"),
     "prints": CAMPPLUS},
]
# The protocol on Windows and Linux, and on a Mac that asks for it (`--model`): the same model as the Mac's, as GGUF on
# llama.cpp's own server, which has ready builds for all three. Never fetched unasked, as the Mac's.
GGUF = [{"id": "qwen3.5-9b-gguf", "type": "llm", "name": "Qwen3.5 9B (GGUF)", "langs": ["sv", "en"], "model": "unsloth/Qwen3.5-9B-GGUF",
         "revision": "3885219b6810b007914f3a7950a8d1b469d598a5",
         "size": 5_680_522_464, "license": "Apache 2.0", "default": [], "min_ram_gb": 16, "adapter": "llama"}] if LOCAL_MODEL else []
REGISTRY = (MLX if BACKEND == "mlx" else ONNX) + GGUF
INTERNAL = ("adapter", "chunk", "extra", "prints", "revision")  # not in `byggmote models --json`
# What a model needs from its repo (glob patterns); the rest (README, .gitattributes) isn't fetched.
FILES = {"mlx": ["config.json", "model.safetensors", "tokenizer.model"], "mlx-lm": ["*.json", "*.safetensors", "*.jinja"],
         "onnx": ["config.json", "*.int8.onnx", "vocab.txt", "tokenizer.model"], "sherpa": [CAMPPLUS.replace("/", "_") + ".onnx"],
         "llama": ["*-Q4_K_M.gguf"]}
DONE = {"mlx": "*.safetensors", "mlx-lm": "*.safetensors", "onnx": "encoder-model.int8.onnx",
        "sherpa": FILES["sherpa"][0], "llama": FILES["llama"][0]}  # there once fetched


def local(entry: dict) -> Path | None:
    """A model shipped with the app, unpacked in BYGGMOTE_MODELS/<id> (the app sets Byggmöte.app/Contents/Resources/models)."""
    root = os.environ.get("BYGGMOTE_MODELS") or Path(__file__).parents[2] / "models"  # a development checkout: engine/models
    d = root and Path(root).expanduser() / entry["id"]
    return d if d and (d / "config.yaml").exists() else None


def _cache(repo: str) -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE
    return Path(HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}"


def downloaded(entry: dict) -> bool:
    if local(entry):
        return True
    have = lambda repo, pat, rev: any((_cache(repo) / "snapshots" / rev).glob(pat))
    return have(entry["model"], DONE.get(entry["adapter"], "config.yaml"), entry["revision"]) and (
        "extra" not in entry or have(*entry["extra"]))


def listing() -> list[dict]:
    return [{k: v for k, v in e.items() if k not in INTERNAL} | {"downloaded": downloaded(e)} for e in REGISTRY]


def default(kind: str, lang: str | None = None) -> dict:
    for e in REGISTRY:
        if e["type"] == kind and (lang in e["default"] or "*" in e["default"]):
            return e
    raise ValueError(f"no {kind} model" + (f" for language {lang!r}" if lang else ""))


def download(ids: list[str], emit) -> int:
    """`byggmote models download`: each model in turn (default models without ids); one failure doesn't stop the next."""
    by = {e["id"]: e for e in REGISTRY}
    if bad := [i for i in ids if i not in by]:
        emit({"event": "error", "message": f"unknown model: {', '.join(bad)}"})
        return 2
    todo = [by[i] for i in dict.fromkeys(ids)] or [e for e in REGISTRY if e["default"]]
    ok, failed = [], []
    for e in todo:
        try:
            ensure(e, emit)
            ok.append(e["id"])
            emit({"event": "downloaded", "id": e["id"]})
        except Exception as x:
            traceback.print_exc(file=sys.stderr)
            failed.append(e["id"])
            emit({"event": "error", "id": e["id"], "message": short_error(x)})
    emit({"event": "done", "downloaded": ok, "failed": failed})
    return 1 if failed else 0


def discard(ids: list[str]) -> list[str]:
    """`byggmote models discard`: what a download stopped before its end left in the HF cache, the partial files and the files
    no snapshot links yet, goes. A downloaded model is not touched. The app runs it after it stops a download, never during one."""
    by = {e["id"]: e for e in REGISTRY}
    if bad := [i for i in ids if i not in by]:
        raise ValueError(f"unknown model: {', '.join(bad)}")
    gone = []
    for e in (by[i] for i in dict.fromkeys(ids)):
        c = _cache(e["model"])
        if downloaded(e) or not (c / "blobs").is_dir():
            continue
        linked = {p.resolve() for p in (c / "snapshots").rglob("*") if p.is_symlink()}
        left = [b for b in (c / "blobs").iterdir() if b.resolve() not in linked]
        for b in left:
            try:
                b.unlink(missing_ok=True)
            except OSError:  # Windows: a process that just ended can hold it a moment; the next discard or download takes it
                traceback.print_exc(file=sys.stderr)
        if left:
            gone.append(e["id"])
    return gone


def _check_space(path: Path, need: int):
    while not path.exists():
        path = path.parent
    if shutil.disk_usage(path).free < need:
        raise OSError(errno.ENOSPC, "not enough disk space")


def ensure(entry: dict, emit):
    """Download into the HF cache with byte progress events. No-op when cached.
    Each file goes to blobs/<etag>.incomplete over HTTP with Range, so a quit resumes where it stopped
    (huggingface_hub's own download, Xet included, restarts under a new random name every time)."""
    if downloaded(entry):
        return
    from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_download, hf_hub_url, snapshot_download
    from huggingface_hub.file_download import http_get
    from huggingface_hub.utils import build_hf_headers
    from tqdm.auto import tqdm
    import truststore
    truststore.inject_into_ssl()  # the OS's certificates, not certifi's: a company's TLS inspection signs with its own root
    if entry.get("extra"):
        repo, file, rev = entry["extra"]
        hf_hub_download(repo, file, revision=rev)  # small, no progress
    repo, allow = entry["model"], FILES.get(entry["adapter"])
    rev = entry["revision"]
    info, blobs = HfApi().model_info(repo, revision=rev), _cache(repo) / "blobs"
    files = []  # (url, blob, size)
    for s in info.siblings:
        if not allow or any(fnmatch(s.rfilename, p) for p in allow):
            url = hf_hub_url(repo, s.rfilename, revision=rev)
            m = get_hf_file_metadata(url)
            files.append((url, blobs / m.etag, m.size))
    part = lambda blob: blob.with_name(blob.name + ".incomplete")
    for p in set(blobs.glob("*.incomplete")) - {part(b) for _, b, _ in files}:
        p.unlink(missing_ok=True)  # left by an older version or huggingface_hub, never resumable
    total = sum(n for *_, n in files)
    have = lambda: sum(_size(b) or _size(part(b)) for _, b, _ in files)
    _check_space(blobs, total - have())

    class Quiet(tqdm):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw | {"disable": True})

    stop = threading.Event()

    def poll():
        while not stop.wait(1.0):
            emit({"event": "download", "model": repo, "done": min(have(), total), "total": total})

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        for url, blob, size in files:
            if blob.exists():
                continue
            p = part(blob)
            blob.parent.mkdir(parents=True, exist_ok=True)
            if _size(p) > size:
                p.unlink()
            with open(p, "ab") as f:
                http_get(url, f, resume_size=f.tell(), expected_size=size, tqdm_class=Quiet,
                         headers=build_hf_headers() | {"Accept-Encoding": "identity"})
            if len(blob.name) == 64 and _sha256(p) != blob.name:  # LFS etag = sha256; a bad resume starts over
                p.unlink()
                raise OSError(f"download of {repo} was corrupt, try again")
            replace(p, blob)
        snapshot_download(repo, revision=rev, allow_patterns=allow, tqdm_class=Quiet)  # the blobs are there: only links them
    finally:
        stop.set()
        t.join()
    emit({"event": "download", "model": repo, "done": total, "total": total})


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _sha256(p: Path) -> str:
    with open(p, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def device() -> str:
    """For the speaker model: PyTorch with MLX, else the CPU. ASR runs on ASR_DEVICE."""
    if BACKEND == "onnx":
        return "cpu"
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def free_gpu():
    """MLX's and PyTorch's caches keep freed buffers (load-time, a deleted model). Only frameworks already loaded."""
    if "mlx.core" in sys.modules:
        sys.modules["mlx.core"].clear_cache()
    if "torch" in sys.modules and sys.modules["torch"].backends.mps.is_available():
        sys.modules["torch"].mps.empty_cache()


class Tdt:
    """Parakeet-family TDT models: chunks, words from tokens, and the vocabulary's corrections. A subclass encodes a
    chunk, decodes it plainly, and decodes frames again with the phrase bonus (`_boosted`); `ratio` is seconds per frame."""
    PAD = 3  # words of context on each side of a word near a term, decoded again with the boost
    LEAD = 2.0  # seconds decoded before those: starting cold, the decoder missed 12 of 28 fixes in a meeting (#429)

    def __init__(self, entry: dict):
        self.entry = entry
        self.vocab, self.booster, self.fixes = None, (None, None), []
        # ~5 min chunks unless the model says (`chunk`), cut at the quietest 0.1 s within ±a tenth of it: a wider
        # window cut 0.1 s chunks off 30 s ones
        self.chunk = entry.get("chunk", 300) * SR
        self.window = self.chunk // 10

    def _tree(self, size: int):
        """The phrase boosting tree for the vocabulary's terms; alpha 1, score 2 measured with NeMo in #329."""
        if self.booster[0] != self.vocab.terms:
            from .phrase_boost import PhraseBoost
            self.booster = (self.vocab.terms, PhraseBoost(self.vocab.terms, self.tokenizer, size, context_score=2.0))
        return self.booster[1]

    def cuts(self, a: np.ndarray, chunk: int | None = None, window: int | None = None) -> list[int]:
        """Cuts at the quietest 0.1 s within `chunk` ± `window` samples of the last cut, the model's unless given. A cut
        needs only the audio up to the end of its window, so the cuts of a recording that grows stay where they are."""
        chunk, window = chunk or self.chunk, window or self.window
        pos, out, frame = 0, [0], SR // 10
        while len(a) - pos > chunk + window:
            lo = pos + chunk - window
            w = a[lo:lo + 2 * window]
            rms = np.sqrt((w[: len(w) // frame * frame].reshape(-1, frame) ** 2).mean(axis=1))
            pos = lo + int(rms.argmin()) * frame + frame // 2
            out.append(pos)
        return out + [len(a)]

    @staticmethod
    def _words(tokens, off: float) -> list[dict]:
        """Tokens to words: a token that starts with a space starts a word; punctuation stays on its word."""
        out = []
        for t in tokens:
            if t.text.startswith(" ") or not out:
                out.append({"w": t.text.strip(), "s": round(t.start + off, 2), "e": round(t.end + off, 2)})
            else:
                out[-1]["w"] += t.text
                out[-1]["e"] = round(t.end + off, 2)
        return [w for w in out if w["w"]]

    def _near(self, words: list[dict], enc, n: int, off: float) -> tuple[list[dict], list[dict]]:
        """Words near a term, with PAD words around them, decoded again with the boost over only their frames (#429:
        a 5-minute chunk of a meeting nearly always has something near a term). The words and the fixes made."""
        wins = []
        for i, j in self.vocab.near([w["w"] for w in words]):
            a, b = max(0, i - self.PAD), min(len(words), j + self.PAD)
            if wins and a <= wins[-1][1]:
                wins[-1][1] = max(wins[-1][1], b)
            else:
                wins.append([a, b])
        out, fixes, done, r = [], [], 0, self.ratio
        for a, b in wins:
            f0 = max(0, int((words[a]["s"] - self.LEAD - off) / r))
            f1 = min(n, math.ceil((words[b - 1]["e"] - off) / r) + 1)
            got, f = self.vocab.merge(words[a:b], self._words(self._boosted(enc, f0, f1), off))
            out += words[done:a] + got
            fixes += f
            done = b
        return out + words[done:], fixes

    def words(self, a: np.ndarray, progress, vocab=None) -> list[dict]:
        """`vocab` (context.Vocab) corrects terms; what it changed is in `fixes` afterwards, and a corrected word has
        `heard`. Plain decoding first; when words are near a term, a meeting decodes only them again with phrase
        boosting, dictation the whole clip."""
        b = self.cuts(a)
        out, fixes = [], []
        self.vocab = vocab if vocab and vocab.terms else None
        for lo, hi in zip(b, b[1:]):
            if hi - lo < SR // 10:  # the log-mel needs a few frames; NeMo returned nothing here too
                continue
            enc, n = self._encode(a[lo:hi])
            chunk = self._words(self._decode(enc, n), lo / SR)
            if self.vocab and self.vocab.meeting:
                chunk, f = self._near(chunk, enc, int(n[0]), lo / SR)
                fixes += f
            elif self.vocab and self.vocab.near([w["w"] for w in chunk]):
                chunk, f = self.vocab.merge(chunk, self._words(self._boosted(enc, 0, int(n[0])), lo / SR))
                fixes += f
            out += chunk
            del enc
            self._free()
            progress(hi / len(a))
        if vocab:
            out, f = vocab.replace(out)
            fixes += f
        self.fixes = fixes
        return out

    def span(self, a: np.ndarray, off: float, lo: float, hi: float | None, vocab=None) -> tuple[list[dict], list[dict]]:
        """A dictation's chunk (#1285): `a` starts `off` s into the recording and is decoded as one clip, as `words`
        decodes a dictation, but only the words that start from `lo` to `hi` s (None: to the end) are kept; the rest was
        context. The words and the fixes made, without the vocabulary's replacements, which run over the whole text."""
        self.vocab = vocab if vocab and vocab.terms else None
        keep = lambda ws: [w for w in ws if lo <= w["s"] and (hi is None or w["s"] < hi)]
        enc, n = self._encode(a)
        out, fixes = keep(self._words(self._decode(enc, n), off)), []
        if self.vocab and self.vocab.near([w["w"] for w in out]):
            out, fixes = self.vocab.merge(out, keep(self._words(self._boosted(enc, 0, int(n[0])), off)))
        del enc
        self._free()
        return out, fixes

    def _free(self):
        pass


class Mlx(Tdt):
    """Parakeet-family TDT models on MLX (parakeet-mlx). Features, quantized loading and phrase boosting as in
    KlangAI/pianissimo-sv-mlx's `pianissimo_mlx.py` (CC BY 4.0); measured against NeMo in #570."""
    CACHE = 512 << 20  # MLX keeps freed buffers; unlimited, a 1 h meeting peaked at 5.7 GB instead of 3.6

    @property
    def ratio(self) -> float:
        return self.model.time_ratio

    def load(self, dev: str = ""):
        import json
        import mlx.core as mx
        import mlx.nn as nn
        from huggingface_hub import snapshot_download
        from parakeet_mlx.utils import from_config
        mx.set_cache_limit(self.CACHE)
        path = Path(snapshot_download(self.entry["model"], revision=self.entry["revision"], allow_patterns=FILES["mlx"],
                                      local_files_only=True))
        cfg = json.loads((path / "config.json").read_text(encoding="utf-8"))
        model = from_config(cfg)
        q = cfg.get("quantization")

        def quantize(bits, group_size):
            nn.quantize(model, group_size=group_size, bits=bits,
                        class_predicate=lambda p, m: isinstance(m, nn.Linear) and p.startswith("encoder.layers."))
        if q:
            quantize(q["bits"], q["group_size"])
        model.load_weights(str(path / "model.safetensors"))
        if not q:  # Parakeet's MLX repo is fp32: 8-bit like Pianissimo's, ~1.8 GB less in memory
            quantize(8, 64)
        mx.eval(model.parameters())
        self.model, self.tokenizer = model, path / "tokenizer.model"

    def _features(self, audio):
        """NeMo's log-mel featurizer: parakeet-mlx's own differs slightly (+0.2 pp WER, Klang)."""
        import mlx.core as mx
        args = self.model.preprocessor_config
        n_fft, win = args.n_fft, int(args.window_size * args.sample_rate)
        hop = int(args.window_stride * args.sample_rate)
        x = mx.concatenate([audio[:1], audio[1:] - 0.97 * audio[:-1]])
        x = mx.pad(x, [(n_fft // 2, n_fft // 2)])
        frames = mx.as_strided(x, shape=((x.shape[0] - n_fft) // hop + 1, n_fft), strides=(hop, 1))
        window = mx.array(np.pad(np.hanning(win), (n_fft - win) // 2).astype(np.float32))
        power = mx.abs(mx.fft.rfft(frames * window)) ** 2
        logmel = mx.log(mx.matmul(power, args._filterbanks.T.astype(mx.float32)) + 2 ** -24)
        valid = audio.shape[0] // hop
        logmel = logmel[:valid]
        mean = logmel.mean(axis=0, keepdims=True)
        std = mx.sqrt(((logmel - mean) ** 2).sum(axis=0, keepdims=True) / (valid - 1))
        return mx.expand_dims((logmel - mean) / (std + 1e-5), 0)

    def _encode(self, a: np.ndarray):
        import mlx.core as mx
        enc, n = self.model.encoder(self._features(mx.array(a)))
        mx.eval(enc, n)
        return enc, n

    def _decode(self, enc, n):
        return self.model.decode(enc, n)[0][0]

    def _free(self):
        import mlx.core as mx
        mx.clear_cache()

    def _boosted(self, enc, lo: int, hi: int):
        """Greedy TDT decoding of frames `lo` to `hi` with the vocabulary's phrase bonus."""
        import mlx.core as mx
        from parakeet_mlx import tokenizer
        from parakeet_mlx.alignment import AlignedToken
        tree, m = self._tree(len(self.model.vocabulary)), self.model
        blank = len(m.vocabulary)
        out, last, hidden, state, step, new = [], None, None, 0, lo, 0
        while step < hi:
            dec, (h, c) = m.decoder(mx.array([[last]]) if last is not None else None, hidden)
            joint = m.joint(enc[:, step:step + 1], dec.astype(enc.dtype))
            logits = joint[0, 0, :, :blank + 1]
            tok, dur = int(mx.argmax(logits)), int(mx.argmax(joint[0, 0, :, blank + 1:]))
            if tok != blank:
                bonus, nxt = tree.scores(state)
                tok = int(np.argmax(np.array(logits[0, :blank].astype(mx.float32)) + bonus))
                state = int(nxt[tok])
                out.append(AlignedToken(tok, start=step * m.time_ratio, duration=m.durations[dur] * m.time_ratio,
                                        text=tokenizer.decode([tok], m.vocabulary)))
                last, hidden = tok, (h.astype(enc.dtype), c.astype(enc.dtype))
            step += m.durations[dur]
            new = 0 if m.durations[dur] else new + 1
            if new and m.max_symbols is not None and new >= m.max_symbols:
                step, new = step + 1, 0
        return out


class Token(NamedTuple):
    text: str
    start: float
    end: float


class Onnx(Tdt):
    """Parakeet-family TDT models as ONNX int8 on the CPU (onnx-asr), as on Windows (#792). Decoding and phrase
    boosting as in KlangAI/pianissimo-sv-onnx's `pianissimo_onnx.py` (CC BY 4.0). Chunks per model (`chunk`): longer
    ones peaked over 3 GB for an hour-long meeting on the X1 Carbon, and Parakeet's export slows down per minute."""
    THREADS = 4  # 8 (hyperthreads) gave the same time on the X1 Carbon's 4 cores (#792)
    ratio = 0.08  # 10 ms features, subsampled 8 times

    def load(self, dev: str = ""):
        import onnx_asr
        import onnxruntime as rt
        from huggingface_hub import hf_hub_download, snapshot_download
        path = Path(snapshot_download(self.entry["model"], revision=self.entry["revision"], allow_patterns=FILES["onnx"],
                                      local_files_only=True))
        so = rt.SessionOptions()
        so.intra_op_num_threads, so.inter_op_num_threads = min(self.THREADS, os.cpu_count() or 1), 1
        so.enable_mem_pattern = False  # it plans memory per chunk length: an hour peaked at 3.7 GB instead of 2.5 (#793)
        self.asr = onnx_asr.load_model("nemo-conformer-tdt", path, quantization="int8", sess_options=so).asr
        extra = self.entry.get("extra")
        self.tokenizer = (Path(hf_hub_download(extra[0], extra[1], revision=extra[2], local_files_only=True)) if extra
                          else path / "tokenizer.model")

    def _encode(self, a: np.ndarray):
        return self.asr._encode(*self.asr._preprocessor(a[None], np.array([len(a)], dtype=np.int64)))

    def _decode(self, enc, n):
        return self._tdt(enc, 0, int(n[0]))

    def _boosted(self, enc, lo: int, hi: int):
        return self._tdt(enc, lo, hi, self._tree(self.asr._blank_idx))

    def _tdt(self, enc, lo: int, hi: int, tree=None) -> list[Token]:
        """onnx-asr's greedy TDT loop over frames `lo` to `hi`, with the phrase bonus when there is a `tree`."""
        asr, blank = self.asr, self.asr._blank_idx
        out, toks, state, boost, t, emitted = [], [], asr._create_state(), 0, lo, 0
        while t < hi:
            logits, step, nxt = asr._decode(toks, state, enc[0, t])
            tok = int(logits.argmax())
            if tok != blank:
                if tree:
                    bonus, after = tree.scores(boost)
                    tok = int(np.argmax(logits[:blank] + bonus))
                    boost = int(after[tok])
                state = nxt
                toks.append(tok)
                out.append(Token(asr._vocab[tok], t * self.ratio, (t + max(step, 0)) * self.ratio))
                emitted += 1
            if step > 0:
                t, emitted = t + step, 0
            elif tok == blank or emitted == asr._max_tokens_per_step:
                t, emitted = t + 1, 0
        return out


class Pyannote:
    # Shares of the step's time: on a 39 min meeting segmentation took 20 s, embeddings 77 s (#1158)
    PHASES = {"segmentation": (0.0, 0.2), "embeddings": (0.2, 0.95)}

    def __init__(self, entry: dict):
        self.entry = entry

    def load(self, dev: str):
        import torch
        from pyannote.audio import Pipeline
        from huggingface_hub import snapshot_download
        path = local(self.entry) or snapshot_download(self.entry["model"], revision=self.entry["revision"], local_files_only=True)
        self.pipe = Pipeline.from_pretrained(path).to(torch.device(dev))
        # Default batches peaked at 6.8 GB on a 1 h meeting, 8 at 2.8 GB for ~23 % more time (#570)
        self.pipe.segmentation_batch_size = self.pipe.embedding_batch_size = 8

    def diarize(self, a: np.ndarray, lo: int | None, hi: int | None, progress):
        import torch

        def hook(name, _art, file=None, total=None, completed=None):
            if name in self.PHASES and total and completed is not None:
                p0, p1 = self.PHASES[name]
                progress(p0 + (p1 - p0) * min(completed, total) / total)  # segmentation counts past total

        kw = {k: v for k, v in (("min_speakers", lo), ("max_speakers", hi)) if v}
        o = self.pipe({"waveform": torch.from_numpy(a)[None], "sample_rate": SR}, hook=hook, **kw)
        turns = [(round(t.start, 2), round(t.end, 2), s)
                 for t, _, s in o.exclusive_speaker_diarization.itertracks(yield_label=True)]
        emb = {}
        if o.speaker_embeddings is not None:
            emb = {s: [round(float(x), 5) for x in o.speaker_embeddings[i]]
                   for i, s in enumerate(o.speaker_diarization.labels())}
        progress(1.0)
        return turns, emb


def _by_speaker(turns: list) -> dict:
    by = {}
    for t in turns:
        by.setdefault(t[2], []).append(t)
    return by


SMALL, SMALL_MIN = 0.005, 5.0  # a speaker under this share of the meeting (at least SMALL_MIN s) is a fragment


def fold(turns: list, prints, seconds: float, keep: int = 1, cap: int | None = None) -> list:
    """Fragments join the speaker with the nearest voice print, or, too short to embed, the speaker whose turn is
    nearest. `prints(turns)` is a speaker's print from their turns, None when there is none. The `keep` largest
    speakers always stay, at most `cap` do. A clip where nobody reaches the floor stays as it is, up to `cap`.
    Every OS (#1213, #1463): a few words in another voice became a speaker of their own, and on Tim's meetings most
    such speakers were named as a bigger speaker in the same meeting."""
    by = _by_speaker(turns)
    dur = {k: sum(e - s for s, e, _ in kt) for k, kt in by.items()}
    floor = max(SMALL_MIN, SMALL * seconds)
    ranked = sorted(dur, key=dur.get, reverse=True)[:cap]
    big = ranked if not dur or max(dur.values()) < floor else \
        [k for i, k in enumerate(ranked) if dur[k] >= floor or i < keep]
    if len(big) == len(by):
        return turns
    pr = {}
    for k, kt in by.items():
        if (v := prints(kt)) is not None and (n := np.linalg.norm(v)) and np.isfinite(n):
            pr[k] = np.asarray(v) / n
    near = [b for b in big if b in pr]
    to = {k: k for k in big}
    for k in by.keys() - to.keys():
        if k in pr and near:
            to[k] = max(near, key=lambda b: pr[k] @ pr[b])
        else:
            s0, e0 = by[k][0][:2]
            to[k] = min((t for t in turns if t[2] in big), key=lambda t: max(t[0] - e0, s0 - t[1], 0))[2]
    return [(s, e, to[k]) for s, e, k in turns]


class Sherpa:
    """Speakers with sherpa-onnx on the CPU (Windows, #792): segmentation-3.0 int8, CAM++ embeddings, agglomerative
    clustering. Step 5 s: 1.6 min per meeting hour on the X1 Carbon. Threshold 0.9 and `fold` (#1213): 1.1 merged
    people who say little into the main speaker (4 in a short meeting became 2), 0.9 alone keeps them but leaves many
    fragments of a few seconds."""
    SHIFT, THRESHOLD, THREADS = 0.5, 0.9, 4
    PRINT = 60  # seconds of a speaker's longest turns behind their voice print

    def __init__(self, entry: dict):
        self.entry = entry

    def load(self, dev: str = ""):
        import sherpa_onnx as so
        from huggingface_hub import hf_hub_download
        repo, file, rev = self.entry["extra"]
        seg = hf_hub_download(repo, file, revision=rev, local_files_only=True)
        emb = hf_hub_download(self.entry["model"], FILES["sherpa"][0], revision=self.entry["revision"], local_files_only=True)
        n = min(self.THREADS, os.cpu_count() or 1)
        embedding = so.SpeakerEmbeddingExtractorConfig(model=emb, num_threads=n)
        self.config = lambda k: so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=seg, window_shift_ratio=self.SHIFT),
                num_threads=n),
            embedding=embedding, clustering=so.FastClusteringConfig(num_clusters=k, threshold=self.THRESHOLD),
            min_duration_on=0.3, min_duration_off=0.5)
        self.sd = so.OfflineSpeakerDiarization(self.config(-1))
        self.ex = so.SpeakerEmbeddingExtractor(embedding)

    def diarize(self, a: np.ndarray, lo: int | None, hi: int | None, progress):
        def once(k: int):
            self.sd.set_config(self.config(k))
            return self.sd.process(a, callback=lambda done, total: progress(0.9 * done / total) or 0).sort_by_start_time()

        def to_turns(segs):
            return [(round(x.start, 2), round(x.end, 2), f"SPEAKER_{x.speaker:02d}") for x in segs]

        # an exact count or a threshold, never a range: above it the merge stops at hi, below it again with lo
        ts = fold(to_turns(once(lo if lo and lo == hi else -1)), lambda kt: self._print(a, kt), len(a) / SR, keep=lo or 1, cap=hi)
        if lo and len({t[2] for t in ts}) < lo:
            ts = to_turns(once(lo))
        emb = {k: v for k, kt in _by_speaker(ts).items() if (v := self._print(a, kt))}
        progress(1.0)
        return ts, emb

    def _print(self, a: np.ndarray, turns: list) -> list[float] | None:
        """CAM++ over the speaker's longest turns, up to PRINT seconds; None when too short to embed."""
        clip, left = [], self.PRINT * SR
        for s, e, _ in sorted(turns, key=lambda t: t[0] - t[1]):
            clip.append(a[int(s * SR):int(e * SR)][:left])
            left -= len(clip[-1])
            if left <= 0:
                break
        st = self.ex.create_stream()
        st.accept_waveform(SR, np.concatenate(clip))
        st.input_finished()
        return [round(float(x), 5) for x in self.ex.compute(st)] if self.ex.is_ready(st) else None


TOO_LONG = "meeting too long for the local model"
TURN = re.compile(r"\[\d+:\d\d(?::\d\d)?\] ")  # a transcript line as transcript.txt writes it: [12:03] Anna: …
PARTS = ("(The meeting is too long to read in one go. Instead of the transcript, here are the answers for its consecutive "
         "parts, in order. Write one answer for the whole meeting from them; where a later part corrects an earlier "
         "one, the later part wins.)\n\n")


class MlxLm:
    """A chat model on MLX (mlx-lm): the prompt as one user message, thinking off, greedy. A prompt over MAX_IN tokens
    is answered in parts (its transcript lines split evenly), then the parts' answers in one more pass."""
    # 40k tokens in: ~1 h 40 min of Swedish; 37.9k peaked at 8.6 GB (#569). Out: the minutes with their topics and issue suggestions, as JSON.
    MAX_IN, MAX_OUT = 40_000, 8192
    STEP = 512  # prefill chunk: mlx-lm's 2048 peaked 1.5 GB higher on a 1 h meeting at the same speed (#569)

    def __init__(self, entry: dict):
        self.entry = entry

    def load(self):
        import mlx.core as mx
        from huggingface_hub import snapshot_download
        from mlx_lm import load
        mx.set_cache_limit(Mlx.CACHE)
        self.model, self.tokenizer = load(snapshot_download(self.entry["model"], revision=self.entry["revision"],
                                                          allow_patterns=FILES["mlx-lm"], local_files_only=True))

    def _ids(self, prompt: str) -> list[int]:
        return self.tokenizer.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True,
                                                  enable_thinking=False)

    def _generate(self, ids: list[int]) -> str:
        from mlx_lm import stream_generate
        out, r = [], None
        for r in stream_generate(self.model, self.tokenizer, ids, max_tokens=self.MAX_OUT, prefill_step_size=self.STEP):
            out.append(r.text)
        if not r or r.finish_reason != "stop":
            raise RuntimeError("the answer did not finish")
        return unfence("".join(out))

    def summarize(self, prompt: str, schema: dict | None = None) -> str:
        """`schema` is not used: mlx-lm cannot hold an answer to one, so the prompt asks for the form and the caller checks it."""
        ids = self._ids(prompt)
        if len(ids) <= self.MAX_IN:
            return self._generate(ids)
        lines = prompt.splitlines(keepends=True)
        turns = [i for i, line in enumerate(lines) if TURN.match(line)]
        if not turns:
            raise ValueError(TOO_LONG)
        head, body, tail = "".join(lines[:turns[0]]), lines[turns[0]:turns[-1] + 1], "".join(lines[turns[-1] + 1:])
        frame = len(self._ids(head + tail))
        if frame >= self.MAX_IN:
            raise ValueError(TOO_LONG)
        for k in range(math.ceil((len(ids) - frame) / (self.MAX_IN - frame)), len(body) + 1):
            parts = [self._ids(head + p + tail) for p in split(body, k)]
            if max(map(len, parts)) <= self.MAX_IN:  # split by characters, so a dense part may need one more
                break
        else:
            raise ValueError(TOO_LONG)
        last = self._ids(head + PARTS + "\n".join(self._generate(p) for p in parts) + tail)
        if len(last) > self.MAX_IN:
            raise ValueError(TOO_LONG)
        return self._generate(last)


def split(lines: list[str], k: int) -> list[str]:
    """`lines` in up to `k` consecutive runs of about the same length."""
    total, done, out = sum(map(len, lines)), 0, [[]]
    for line in lines:
        if out[-1] and done >= len(out) * total / k:
            out.append([])
        out[-1].append(line)
        done += len(line)
    return ["".join(p) for p in out]


def unfence(text: str) -> str:
    """The answer without a code fence around all of it (```json … ```), ending in one newline."""
    t = text.strip()
    if t.startswith("```") and t.endswith("```") and "\n" in t:
        t = t[t.index("\n") + 1:-3].strip()
    return t + "\n"


def llama_server() -> Path:
    """llama.cpp's server: the app's own (BYGGMOTE_LLAMA_SERVER), a development checkout's in engine/bin, else one on the path."""
    name = "llama-server.exe" if WINDOWS else "llama-server"
    if p := os.environ.get("BYGGMOTE_LLAMA_SERVER"):
        return Path(p).expanduser()
    if found := sorted(Path(__file__).parents[2].glob(f"bin/llama-*/**/{name}")):
        return found[-1]
    if p := shutil.which(name):
        return Path(p)
    raise RuntimeError("llama-server is not installed")


class LlamaServer:
    """A chat model as GGUF on llama.cpp's server. Started for one answer and stopped after it: on 127.0.0.1 only, behind a
    key made for the run, never downloading, and asked past any proxy the computer has, so the transcript stays here.
    The prompt as one user message, thinking off, greedy, as MlxLm. With a `schema` the server holds the answer to it."""
    MAX_IN, MAX_OUT = MlxLm.MAX_IN, MlxLm.MAX_OUT
    STEP = 4096  # the context is made as large as the prompt needs, in steps: each token of it costs memory
    SPARE = 512  # tokens for the chat template around the prompt
    READY = 600  # seconds for the model to load, from a slow disk too

    def __init__(self, entry: dict):
        self.entry = entry

    def load(self):
        from huggingface_hub import snapshot_download
        self.server = llama_server()
        d = Path(snapshot_download(self.entry["model"], revision=self.entry["revision"], allow_patterns=FILES["llama"],
                                   local_files_only=True))
        self.model = next(d.glob(DONE["llama"]))

    def _ctx(self, tokens: int) -> int:
        return math.ceil((min(tokens, self.MAX_IN) + self.MAX_OUT + self.SPARE) / self.STEP) * self.STEP

    def _command(self, port: int, ctx: int) -> list[str]:
        return [str(self.server), "-m", str(self.model), "--host", "127.0.0.1", "--port", str(port), "-c", str(ctx), "-np", "1",
                "--reasoning", "off", "--no-webui", "--offline", "--no-warmup"]

    @contextmanager
    def _serve(self, ctx: int):
        """The server with a context of `ctx` tokens; yields `ask(path, body)`, which posts JSON (gets without a body)."""
        import secrets
        import socket
        import subprocess
        import urllib.error
        import urllib.request
        with socket.socket() as s:  # a free port: the server takes it a moment later
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        key = secrets.token_hex(16)
        try:  # the server prints: to stderr when the engine has one, since stdout is the engine's answer
            sys.stderr.fileno()
            log = sys.stderr
        except (AttributeError, OSError, ValueError):  # a windowless parent, or a stream that is no file
            log = subprocess.DEVNULL
        proc = subprocess.Popen(
            self._command(port, ctx),
            env=os.environ | {"LLAMA_API_KEY": key},  # not an argument: other processes can read those
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0)
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def ask(path: str, body: dict | None = None, timeout: float | None = 30):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", None if body is None else json.dumps(body).encode(),
                                         {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with direct.open(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 503:  # still loading
                    raise
                try:
                    said = json.loads(e.read())["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    said = f"HTTP {e.code}"
                raise RuntimeError(f"llama-server: {said}") from None

        try:
            end = time.monotonic() + self.READY
            while True:
                if proc.poll() is not None:
                    raise RuntimeError(f"llama-server stopped ({proc.returncode})")
                try:
                    ask("/health", timeout=2)
                    break
                except OSError:  # not listening yet, or loading (503)
                    if time.monotonic() > end:
                        raise RuntimeError("the model did not load") from None
                    time.sleep(0.2)
            yield ask
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def summarize(self, prompt: str, schema: dict | None = None) -> str:
        ctx = self._ctx(len(prompt.encode()) // 2)  # a first guess: two bytes a token is more than Swedish needs
        while True:
            with self._serve(ctx) as ask:
                n = len(ask("/tokenize", {"content": prompt})["tokens"])
                if n > self.MAX_IN:
                    raise ValueError(TOO_LONG)
                if self._ctx(n) <= ctx:
                    return self._answer(ask, prompt, schema)
            ctx = self._ctx(n)  # the guess was too small: once more with what the prompt needs

    def _answer(self, ask, prompt: str, schema: dict | None) -> str:
        body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": self.MAX_OUT, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}
        choice = ask("/v1/chat/completions", body, timeout=None)["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise RuntimeError("the answer did not finish")
        return unfence(choice["message"].get("content") or "")


ADAPTERS = {"mlx": Mlx, "onnx": Onnx, "pyannote": Pyannote, "sherpa": Sherpa, "mlx-lm": MlxLm, "llama": LlamaServer}


def adapter(entry: dict):
    return ADAPTERS[entry["adapter"]](entry)
