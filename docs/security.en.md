# Byggmöte on a computer: a security note for IT

[Svenska](security.md) · Contact and reporting: [SECURITY.md](../SECURITY.md)

Written from the code as it is. What the code does not do is not promised here; gaps are under **Gaps**. It covers
`app/` (Electron) and `engine/` (Python), version 0.1.0. The app is not packaged yet, so the paths below are the ones
Electron and the engine choose today.

Sound and the whole transcript never leave the computer. Speech recognition, speakers and the protocol are all done
locally. All that goes to Stommen is the sign-in and, when the person presses Send and approves the list, the
protocol's points.

## What is stored, and where

| What | Where | Contents |
| --- | --- | --- |
| The app's settings | The app's own folder (`userData`, today `byggmote-app`): macOS `~/Library/Application Support/byggmote-app`, Windows `%APPDATA%\byggmote-app`, Linux `~/.config/byggmote-app` | `settings.json`: name, microphone, Recognise Voices on/off, open at login, whether first run is done. No secret. |
| The Stommen connection | Same folder, `stommen.json` (mode 0600) | Stommen's address, the person's and the organization's name, time of the last fetch, and the session token. The token is encrypted with the operating system's keychain (macOS Keychain, Windows DPAPI, Linux libsecret). Where there is no keychain, or only Linux's fixed-key fallback, no token is saved: it lives until the app quits. The password is never kept. |
| The knowledge base | `Documents/Byggmöte` (or the folder the person chooses; the pointer is `~/.config/byggmote/byggmote.json`, Linux `$XDG_CONFIG_HOME/byggmote`) | `areas.json` (projects), `people.json` (names, e-mail, links to Stommen), `learning.json`, and a folder per meeting: `meeting.json` (speakers, transcript, and voice prints when Recognise Voices is on), `transcript.txt`, `audio.m4a`, `protocol.json`, `protocol.md`. Not encrypted, protected by the file system's permissions. Can be a shared folder (OneDrive, Teams) if the person chooses so. |
| A recording in progress | Temp folder, `byggmote-recordings/<id>.webm` | Written a second at a time, removed once the meeting has its own copy. |
| Models | Hugging Face's cache: `~/.cache/huggingface/hub` (or `HF_HOME` / `HF_HUB_CACHE`) | See `NOTICE.md`: five models, 30 MB to 6 GB each, fetched at a fixed commit. |
| The window's own files | `userData` | Chromium's usual cache and storage. The window reads only the app's local files. |

## What is sent, and where to

| To | When | What |
| --- | --- | --- |
| Stommen, `https://app.stommen.io` (the person can give another address; https only, or http for the computer itself) | Sign-in, "Hämta från Stommen", app start when signed in, sign-out | `POST /api/auth/sign-in/email` (e-mail, password), `GET /api/mobile/v1/me`, `/projects`, `/projects/<id>/roles`, `POST /api/auth/sign-out`. Headers `X-App: byggmote` and `X-App-Version`. No redirect is followed. |
| Stommen, `POST /api/mobile/v1/projects/<id>/minutes` | Only when the person presses Send and approves the list, and no check is left | Meeting series and meeting (number, date, length), attendees (name, role), headings, the protocol text, and per point: number, heading, kind, text, role, date, open, how many seconds into the recording it was said, **the line said there** and **who said it**, whether the model wrote it, a person changed it or added it, confirmed amounts. |
| `huggingface.co` (and Hugging Face's own download addresses, which they change as needed) | Only when models are fetched: "Modeller" in first run and Settings, or when a meeting is run and a speech or speaker model is missing. A run never fetches the protocol model. | A request for a fixed commit of a repo, and its files. Nothing about the person or the meeting. Uses the operating system's certificate store, so a company's TLS inspection works. |
| `otel.pyannote.ai` | **On the Mac only, when the speaker model runs, unless something stops it** (see Gaps) | The library's version, a random session id, the audio's length in seconds, the number of speakers. Not sound, not text. |
| The system browser | The person clicks an https link in the window | Nothing from the app. |

Nothing else. The window cannot call out (`Content-Security-Policy: connect-src 'self'`), loads no fonts or scripts
from outside, and the app has no updater, no crash reporting and no analytics (searched in the code). The language
model's server listens on `127.0.0.1` only, with a key made per run, `--offline`, and bypasses the computer's proxy.

**Telemetry.** None in Byggmöte's own code. The exception is pyannote-audio 4.0.7 on the Mac, which has it on from the
start and is switched off with `PYANNOTE_METRICS_ENABLED=false` (checked: with it set nothing is looked up, without it
`otel.pyannote.ai` is). Windows and Linux do not use pyannote. We have not captured the traffic of Chromium in Electron;
see Gaps.

## Processes the app starts

| Process | How | Note |
| --- | --- | --- |
| The engine `byggmote` (Python) | One command per task, from `BYGGMOTE_ENGINE` or `engine/.venv`; inherits the app's environment; stopped when the app quits | Does all processing of recordings, the knowledge base and the model fetch. |
| `ffmpeg`, `ffprobe` | By the engine, from `PATH` | Not shipped and not pinned. |
| `llama-server` (llama.cpp) | By the engine, once per protocol; `BYGGMOTE_LLAMA_SERVER`, else `engine/bin`, else `PATH` | `127.0.0.1`, random port, `--offline --no-webui`. Not shipped, no version pinned (CI tests b12590). |
| `taskkill` | Windows, to stop the engine | |
| `id -F` | macOS, for the person's full name | |

The app asks for the microphone and nothing else a page can ask for. The window runs sandboxed, without Node.

## Models and libraries

Name, version, commit and licence: [NOTICE.md](../NOTICE.md). `python3 scripts/check-notice.py` fails when the list does
not match the code, and CI runs it. CI also makes a software bill of materials (SBOM, CycloneDX) for each release:
`scripts/sbom.py`, attached to the release as `byggmote-sbom.cdx.json`. It has every locked package, not `ffmpeg` and
`llama-server`.

## Updating

The app does not update itself. IT installs a new version. A model changes only when a new version changes its commit
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
5. **`ffmpeg` and `llama-server` are not pinned** and do not come with the app, so their version and licence depend on the computer.
6. **The app is not packaged or signed.** There is no installer to approve yet.
7. **Hugging Face's download addresses** (CDN) are not pinned by us and may change; the list of them has not been checked.
