# Origin and licences

## The engine

`engine/` started as a copy of the engine of Tonband 2026.1118.1 by Tim Kilåker (tomrad.se), used and changed with his
permission. The first commit is that engine with the name changed and nothing else, so `git diff` against it shows
what is ours.

Two things in the engine's comments still point at Tonband: a `#123` is an issue in Tonband's tracker, and a
`docs/…` or `SPEC.md` is one of Tonband's documents. Neither is in this repo.

## The models

No model is in the repo. Each is fetched to the computer it runs on, at a fixed commit (`engine/src/byggmote/models.py`).
The licences below are the ones that file records; check them at the source before a release.

| Model                                | Used for                          | Licence            |
| ------------------------------------ | --------------------------------- | ------------------ |
| Pianissimo (KlangAI)                 | Swedish speech recognition        | CC BY 4.0          |
| Parakeet v3 (NVIDIA)                 | English speech recognition        | CC BY 4.0          |
| pyannote speaker-diarization-community-1 | Speakers, on the Mac          | CC BY 4.0          |
| segmentation-3.0 and CAM++           | Speakers, on Windows and Linux    | MIT and Apache 2.0 |
| Qwen3.5 9B                           | The protocol                      | Apache 2.0         |

Qwen3.5 9B is fetched as other people's conversions of Qwen's model: `mlx-community/Qwen3.5-9B-MLX-4bit` for MLX and
`unsloth/Qwen3.5-9B-GGUF` for llama.cpp.

CC BY 4.0 asks for attribution: the app has to name these models and their makers where a user can read it.

## llama.cpp

`llama-server` is from llama.cpp (The ggml authors, MIT). It is not in the repo. An app that ships a build of it ships
its `LICENSE` too.

## What the installers carry

`app/scripts/bundle-engine.sh` puts these next to the engine, each a pinned build, and the installer ships their
licences in `resources/engine/licenses/`:

- Python 3.12 from python-build-standalone (through uv), under the PSF licence, with the engine's packages under theirs.
- `ffmpeg` and `ffprobe`: on Windows and Linux BtbN's LGPL 2.1 builds, on the Mac Martin Riedl's builds, which are
  GPL 3.0. They run as separate programs; the source is at https://ffmpeg.org.
- `llama-server` on Windows and Linux, with llama.cpp's `LICENSE`.

## The app

The app is built on Electron (MIT) and Svelte (MIT). Its fonts are in the app, so nothing is fetched: Inter, Josefin
Sans and JetBrains Mono, each under the SIL Open Font License 1.1.
