# Byggmöte on a computer: a security note for IT

[Svenska](security.md) · Contact and reporting: [SECURITY.md](../SECURITY.md)

Written from the code as it is. What the code does not do is not promised here; gaps are under **Gaps**. It covers
`app/` (Electron) and `engine/` (Python), version 0.1.0, as installers (Windows `.exe`, Linux `.deb` and AppImage, Mac
`.dmg`; `README.md`, Installing). The installers are not signed yet (see Gaps).

Sound and the whole transcript never leave the computer. Speech recognition, speakers and the protocol are all done
locally. All that goes to Stommen is the sign-in and, when the person presses Send and approves the list, the
protocol's points.

## What is stored, and where

| What | Where | Contents |
| --- | --- | --- |
| The app's settings | The app's own folder (`userData`, for an installed app `Byggmote`): macOS `~/Library/Application Support/Byggmote`, Windows `%APPDATA%\Byggmote`, Linux `~/.config/Byggmote` | `settings.json`: name, microphone, Recognise Voices on/off, open at login, whether first run is done. No secret. If the person turns on "open at login", an installed app registers itself as a login item with the operating system (Windows and Mac; on Linux the app does nothing). |
| The Stommen connection | Same folder, `stommen.json` (mode 0600) | Stommen's address, the person's and the organization's name, time of the last fetch, and the session token. The token is encrypted with the operating system's keychain (macOS Keychain, Windows DPAPI, Linux libsecret). Where there is no keychain, or only Linux's fixed-key fallback, no token is saved: it lives until the app quits. The password is never kept. |
| The knowledge base | `Documents/Byggmöte` (or the folder the person chooses; the pointer is `~/.config/byggmote/byggmote.json`, Linux `$XDG_CONFIG_HOME/byggmote`) | `areas.json` (projects), `people.json` (names, e-mail, links to Stommen), `learning.json`, and a folder per meeting: `meeting.json` (speakers, transcript, and voice prints when Recognise Voices is on), `transcript.txt`, `audio.m4a`, `protocol.json`, `protocol.md`, `marks.json` (what was marked during recording). Not encrypted, protected by the file system's permissions. Can be a shared folder (OneDrive, Teams) if the person chooses so. |
| A saved Word or PDF file | The path the person chooses in the dialog | The protocol, with the project's logo and header. Written only when the person saves; the app keeps no copy. |
| A PDF being made | Temp folder, `byggmote-pdf-*` | The protocol text as HTML, to print it; removed right afterwards. |
| A recording in progress | Temp folder, `byggmote-recordings/<id>.webm` | Written a second at a time, removed once the meeting has its own copy. |
| Models | Hugging Face's cache: `~/.cache/huggingface/hub` (or `HF_HOME` / `HF_HUB_CACHE`) | See `NOTICE.md`: five models, 30 MB to 6 GB each, fetched at a fixed commit. |
| The window's own files | `userData` | Chromium's usual cache and storage. The window reads only the app's local files. |

## What is sent, and where to

| To | When | What |
| --- | --- | --- |
| Stommen, `https://app.stommen.io` (the person can give another address; https only, or http for the computer itself) | Sign-in, "Hämta från Stommen", app start when signed in, sign-out | `POST /api/auth/sign-in/email` (e-mail, password), `GET /api/mobile/v1/me`, `/projects`, `/projects/<id>/roles`, `POST /api/auth/sign-out`. Headers `X-App: byggmote` and `X-App-Version`. No redirect is followed. |
| Stommen, `GET /api/mobile/v1/projects/<id>/minutes` | When a sent protocol is opened, and on request | Nothing is sent but the token. The answer says whether the protocol is justerat there, when and by whom. |
| Stommen, `POST /api/mobile/v1/projects/<id>/minutes` | Only when the person presses Send and approves the list, and no check is left | Meeting series and meeting (number, date, length), attendees (name, role), headings, the protocol text, and per point: number, heading, kind, text, role, date, open, how many seconds into the recording it was said, **the line said there** and **who said it**, whether the model wrote it, a person changed it or added it, confirmed amounts. |
| `huggingface.co` (and Hugging Face's own download addresses, which they change as needed) | Only when models are fetched: "Modeller" in first run and Settings, or when a meeting is run and a speech or speaker model is missing. A run never fetches the protocol model. | A request for a fixed commit of a repo, and its files. Nothing about the person or the meeting. Uses the operating system's certificate store, so a company's TLS inspection works. |
| `otel.pyannote.ai` | **On the Mac only, when the speaker model runs, unless something stops it** (see Gaps) | The library's version, a random session id, the pipeline's origin and name, the audio's length in seconds, the number of speakers. Not sound, not text. |
| The system browser | The person clicks an https link in the window | Nothing from the app. |

Nothing else goes out from Byggmöte's own code. The window cannot call out (`Content-Security-Policy: connect-src 'self'`), loads no fonts or scripts
from outside, and the app has no updater, no crash reporting and no analytics (searched in the code). The language
model's server listens on `127.0.0.1` only, with a key made per run, `--offline`, and bypasses the computer's proxy.

**Telemetry.** None in Byggmöte's own code. The exception is pyannote-audio 4.0.7 on the Mac: **it is on by default
today**, Byggmöte does not switch it off, and it is switched off with `PYANNOTE_METRICS_ENABLED=false` (checked: with it set nothing is looked up, without it
`otel.pyannote.ai` is). Windows and Linux do not use pyannote. A network capture of the whole app has **not been made**:
Electron's and Chromium's own traffic is unchecked, so "no telemetry" is only partly established (the code is read, and
the lookup of `otel.pyannote.ai` was seen); see Gaps.

## Processes the app starts

| Process | How | Note |
| --- | --- | --- |
| The engine `byggmote` (Python) | One command per task. An installed app starts its own Python (`resources/engine/python`); otherwise `BYGGMOTE_ENGINE` or `engine/.venv`; inherits the app's environment; stopped when the app quits | Does all processing of recordings, the knowledge base and the model fetch. |
| `ffmpeg`, `ffprobe` | By the engine. An installed app puts its own copy (`resources/engine/bin`) first on the path; a development run uses the computer's | In the installers, pinned builds with a checksum: BtbN (LGPL 2.1) on Windows and Linux, Martin Riedl (GPL 3.0) on the Mac. |
| `llama-server` (llama.cpp) | By the engine, once per protocol; `BYGGMOTE_LLAMA_SERVER`, the installed app's own (`resources/engine/bin/llama`), else `engine/bin`, else `PATH` | `127.0.0.1`, random port, `--offline --no-webui`. In the Windows and Linux installers, build b12590 with a checksum. The Mac installer has none: the Mac uses `mlx-lm` in Python. |
| `taskkill` | Windows, to stop the engine | |
| `id -F` | macOS, for the person's full name | |

The app asks for the microphone and nothing else a page can ask for. The window runs sandboxed, without Node.

## Models and libraries

Name, version, commit and licence: [NOTICE.md](../NOTICE.md). `python3 scripts/check-notice.py` fails when the list does
not match the code, and CI runs it. CI also makes a software bill of materials (SBOM, CycloneDX) for each release:
`scripts/sbom.py`, attached to the release as `byggmote-sbom.cdx.json` when the release is published (the installers are
built by `release.yml` as a draft release). It has every locked package and the models, but not the bundled `ffmpeg`,
`llama-server` and Python: they are in NOTICE.md with version and licence, and in `app/scripts/bundle-engine.sh`.

## Updating

The app does not update itself. IT installs a new version (silently: Windows `/S /allusers`, Linux `apt install`, Mac copy from
the disk image; the commands are in `README.md`). An uninstall removes the program only, not meetings, settings or models. A model changes only when a new version changes its commit
in `models.py`, and it is then fetched at next use.

## Turning Stommen off

- Do not sign in. Without a sign-in the app never calls Stommen, and the step can be skipped in first run.
- Signed in: **Logga ut** in the Stommen view ends the session at Stommen and removes the token from the computer.
- Hard: block `app.stommen.io` (and any other address the person may have given) in the firewall. The app then works
  without Stommen.
- There is no setting that turns the connection off for good for all users (see Gaps).

## Blocking the model download, or using your own copy

1. Block `huggingface.co` and its download addresses, or set `HF_HUB_OFFLINE=1` in the app's environment. Nothing is then fetched; a missing model gives an error.
2. Put the models where the engine looks: the Hugging Face cache, in its folder layout `models--<owner>--<name>/snapshots/<commit>/` with the files for the commit named in `NOTICE.md`. Move the cache with `HF_HOME` or `HF_HUB_CACHE`, or point at your own mirror with `HF_ENDPOINT`.
3. A model counts as fetched when its files are in the cache at exactly that commit. The speaker model on the Mac can also be put in `BYGGMOTE_MODELS/pyannote-community-1` (with `config.yaml`).

The environment variables apply to the engine, which inherits the app's environment. An app started from Finder or the
Start menu does not see a shell's variables: set them in the system (MDM, `launchctl setenv`, a system variable).

## Gaps

Found when this was written. None of it is promised as fixed.

1. **pyannote telemetry on the Mac is on.** Byggmöte does not switch it off. Until then: `PYANNOTE_METRICS_ENABLED=false` in the environment, or block `otel.pyannote.ai`.
2. **No switch to turn Stommen off for everyone.** The sign-in form is always there; no policy or configuration file closes it.
3. **No network capture of the whole app.** Checked: the code, and the lookup of `otel.pyannote.ai` when the engine's library runs. Not checked: Chromium's and Electron's own traffic, or a run of the whole app under capture.
4. **The knowledge base is not encrypted.** Sound, transcripts, names and voice prints are plain files. The protection is the computer's disk encryption and file permissions.
5. **Development runs** (not installed) use the computer's `ffmpeg` and `llama-server`, so their version and licence depend on the computer.
6. **The installers are not signed.** Mac: ad hoc only (not notarised), so Gatekeeper warns. Windows: no code signing, so SmartScreen warns and AppLocker may block. Linux: no signatures. Signing happens only when the certificates are in the repo's secrets (`release.yml`); as of `README.md` today they are not.
7. **Hugging Face's download addresses** (CDN) are not pinned by us and may change; the list of them has not been checked.
