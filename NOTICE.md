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

### Which copy of each model

The commit is the one `models.py` fetches and loads, and the licence is the string it records there (a repo that
supplies one extra file has the licence of the model it is fetched for). `scripts/check-notice.py` fails when this
table and `models.py` differ.

| Repo (Hugging Face)                                | Commit                                   | Licence         |
| -------------------------------------------------- | ---------------------------------------- | --------------- |
| `KlangAI/pianissimo-sv-mlx-8bit`                   | `7b4d528bfb7ce3c66e2a187904f8d86ac39bc6de` | CC BY 4.0       |
| `mlx-community/parakeet-tdt-0.6b-v3`               | `ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15` | CC BY 4.0       |
| `pyannote/speaker-diarization-community-1`         | `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` | CC BY 4.0       |
| `KlangAI/pianissimo-sv-onnx`                       | `63730c6021234f26b9bbae9a07a04fec39e7a52e` | CC BY 4.0       |
| `istupakov/parakeet-tdt-0.6b-v3-onnx`              | `8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce` | CC BY 4.0       |
| `csukuangfj/speaker-embedding-models`              | `0743f301363dec56491a490f6d6cbc9d67f9a3bf` | MIT, Apache 2.0 |
| `csukuangfj/sherpa-onnx-pyannote-segmentation-3-0` | `9403a6902bb58e3d5ae8c7e77c3422de279db2e0` | MIT, Apache 2.0 |
| `unsloth/Qwen3.5-9B-GGUF`                          | `3885219b6810b007914f3a7950a8d1b469d598a5` | Apache 2.0      |
| `mlx-community/Qwen3.5-9B-MLX-4bit`                | `938d8919941c6e7efd3c7150eff7fe9d12afa631` | Apache 2.0      |

## llama.cpp and ffmpeg

`llama-server` is from llama.cpp (The ggml authors, MIT). It is not in the repo, and the code fixes no version of it: the
engine takes the one named by `BYGGMOTE_LLAMA_SERVER`, else one under `engine/bin/`, else one on the path. CI tests
release b12590. An app that ships a build of it ships its `LICENSE` too.

`ffmpeg` and `ffprobe` are on the computer's path and are not in the repo or pinned. Their licence (LGPL or GPL) is the
one of the build the computer has.

## The app

The app is built on Electron (MIT) and Svelte (MIT). Its fonts are in the app, so nothing is fetched: Inter, Josefin
Sans and JetBrains Mono, each under the SIL Open Font License 1.1.

### Libraries

What the engine (`engine/pyproject.toml`, versions from `uv.lock`) and the app (`app/package.json`, versions and
licences from `package-lock.json`) name themselves, build tools included. What these pull in is in the SBOM that CI
makes for each release (`scripts/sbom.py`). A Python library's licence here is the one its project states; the lock has
none, so it is not checked, but the version is. `scripts/check-notice.py` fails when this table and the code differ.

| Library                               | Version | Licence      | Where  |
| ------------------------------------- | ------- | ------------ | ------ |
| `huggingface-hub` | 1.32.0 | Apache-2.0 | engine |
| `mlx-lm` | 0.32.2 | MIT | engine |
| `numpy` | 2.5.3 | BSD-3-Clause | engine |
| `onnx-asr` | 0.12.0 | MIT | engine |
| `parakeet-mlx` | 0.5.2 | Apache-2.0 | engine |
| `pyannote-audio` | 4.0.7 | MIT | engine |
| `sentencepiece` | 0.2.2 | Apache-2.0 | engine |
| `sherpa-onnx` | 1.13.8 | Apache-2.0 | engine |
| `sherpa-onnx-core` | 1.13.8 | Apache-2.0 | engine |
| `soundfile` | 0.14.0 | BSD-3-Clause | engine |
| `torch` | 2.14.0 | BSD-3-Clause | engine |
| `truststore` | 0.10.5 | MIT | engine |
| `@fontsource-variable/inter` | 5.3.0 | OFL-1.1 | app |
| `@fontsource-variable/jetbrains-mono` | 5.3.0 | OFL-1.1 | app |
| `@fontsource-variable/josefin-sans` | 5.3.0 | OFL-1.1 | app |
| `@playwright/test` | 1.65.1 | Apache-2.0 | app |
| `@sveltejs/vite-plugin-svelte` | 7.3.1 | MIT | app |
| `@types/node` | 24.19.2 | MIT | app |
| `docx` | 9.16.0 | MIT | app |
| `electron` | 45.4.1 | MIT | app |
| `electron-vite` | 6.0.0 | MIT | app |
| `svelte` | 5.59.1 | MIT | app |
| `svelte-check` | 4.7.8 | MIT | app |
| `typescript` | 5.9.3 | Apache-2.0 | app |
| `vite` | 8.3.8 | MIT | app |
