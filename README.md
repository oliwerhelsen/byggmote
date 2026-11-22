# Byggmöte

Records a construction meeting, transcribes it and writes the byggmötesprotokoll. Speech recognition, speaker
separation and the language model all run on the computer, so sound and text never leave it. What a person approves
goes on to Stommen as proposals.

**Status:** the engine runs as a CLI, from a recording to a numbered protocol, with either of two local language
models. Its tests and llama.cpp's server run on Windows and Linux on GitHub; a whole meeting has only been transcribed
on the Mac. The app is a first version: it shows a project's meetings, the agenda and a protocol with its transcript
and sound, records a meeting or takes a recording, names the speakers, and lets a person correct the protocol. It
signs in to Stommen as a person and fetches the person's Projekt with their Roller and Kontakter. Nothing is sent to
Stommen yet, a correction is not tied to who is signed in, and the app is not packaged for installing. Still to
build: sending what a person approves to Stommen, justering, and the phone recorder.

Where the engine comes from and what the models' licences ask: `NOTICE.md`.

## The app

Electron with Svelte 5, in `app/`. It has no data of its own: every view is what the engine's commands answer, and the
window reaches the computer only through the calls in `app/src/shared/types.ts`.

    cd app
    npm install
    npm run dev

It uses the engine of the checkout (`engine/.venv`), so install that first, or name another with `BYGGMOTE_ENGINE`.
Start it from a terminal: the engine needs `ffmpeg` on the path. There is no way to add a project in the app, since
projects are to come from Stommen: add one with the engine (below).

    npm run check     the types, main process and views
    npm test          builds the app and drives it against a knowledge base the engine writes (no model runs)

The tests run the window hidden (`BYGGMOTE_HIDDEN=1`), so a run does not take the screen and a click from whoever
sits at the computer cannot land in it. They also show the engine folders with no models in them: a test that asks
for a protocol to be written, by mistake or because an earlier test failed and the app started over, gets an error
and not minutes of a language model. Recording from a microphone to a written protocol is not in them: it needs the
models and several minutes, and has been run by hand with a sound clip played into the app as its microphone.

### Stommen

The app signs in to Stommen the way Stommen's phone app does (ADR-0018 there): `POST /api/auth/sign-in/email` gives a
session token, and every read under `/api/mobile/v1` carries it. The app names itself with `X-App: byggmote`. It
fetches the person's Projekt and each one's Roller and Kontakter (`/projects`, `/projects/{id}/roles`) and hands them
to the engine (`byggmote stommen project`): at sign-in, on "Hämta från Stommen", and when the app starts.

- The token stays in the main process (`app/src/main/stommen.ts`). On disk it is encrypted by the operating system's
  keychain; on a computer without one it lives until the app quits. The window never sees it, and the password is
  not kept anywhere.
- The address is https, or http for this computer's own. A redirect is not followed, so the password and the token
  go to the address the person gave and nowhere else.
- Only the sign-in goes to Stommen. Nothing of a meeting does.
- The requests are made with Node's `http` and `https`, with the headers the app sets and no others. Node's `fetch`
  adds `sec-fetch-mode`, and Stommen then takes the sign-in for a browser's and refuses it for having no Origin.
- An account with two-factor sign-in is told Byggmöte cannot do that yet (Stommen's phone app cannot either).
- A Projekt that is gone from Stommen, or that the person no longer sees there, stays here with its meetings.

`tests/stommen.spec.ts` runs all of this against a stand-in for Stommen on the computer. The tests give the app a
folder of its own to keep things in (`BYGGMOTE_USER_DATA`) and no keychain (`BYGGMOTE_NO_KEYCHAIN=1`), so a run puts
nothing in the keychain of whoever runs it. The keychain path is checked by hand on the Mac only. Against a real
Stommen (a local one, from the branch that added the roles endpoint) the sign-in, the fetch and the sign-out are
checked by hand once: that is where the `fetch` problem above showed, which the stand-in had not caught.

An engine the app started does not outlive it: quitting stops them all, also one that is writing a protocol. That
is checked by hand on the Mac only.

The views follow the sketch at https://claude.ai/artifact/W2NsCiByVoWE7AUV4rGUMZ and use Stommen's design tokens.

## The engine

Python, installed with [uv](https://docs.astral.sh/uv/). It needs `ffmpeg` on the path.

    cd engine
    uv sync
    uv run byggmote models

Speech recognition and the language model download from Hugging Face on first use (`byggmote models download`). The
speaker model on the Mac, pyannote community-1, is gated there: put it in `engine/models/pyannote-community-1/` once.
A development checkout finds it there; an app sets `BYGGMOTE_MODELS`.

`BYGGMOTE_CONFIG=<folder>` gives the engine a knowledge base of its own in that folder, for trying things out without
touching `~/Documents/Byggmöte`.

### From a recording to a protocol

    echo '{"name": "Kv. Eken kontorshus"}' | byggmote areas add
    echo '{"name": "Byggmöte"}' | byggmote series start kv-eken-kontorshus
    byggmote run meeting.m4a --area kv-eken-kontorshus --title "Byggmöte 5" --speakers 3
    byggmote name "<meeting folder>" "Talare 1" "Maria Lindqvist"
    byggmote agenda kv-eken-kontorshus byggmote
    byggmote protocol "<meeting folder>" --series byggmote

`protocol` writes `protocol.json` (the record) and `protocol.md` (the same for reading) into the meeting's folder.

### What the engine decides, not the model

- **No source, nothing shown.** A point is kept only when its quote is in the transcript, and then it points at the line
  where that is said. What the model proposed without one is listed under `dropped`.
- **Numbers.** A point is `<meeting>.<heading>.<n>`. The engine sets it. A point left open follows along under its own
  number until a meeting closes it, so a heading keeps its number for good: rename it or add one last, never move one.
- **Amounts.** Every amount in a point carries a check with the words the recording has, for a person to confirm.
- **Roles.** Responsibility goes to a Roll the project has. A role it lacks becomes a check, never a guess.

### What a person corrects

The model proposes, a person decides. `byggmote correct` is how:

    echo '{"text": "ÄTA 14 beställs till fast pris 86 500 kr.", "open": false}' | byggmote correct change "<meeting folder>" 5.4.1
    echo '{"heading": 4, "kind": "todo", "text": "Pris på ÄTA 15 lämnas.", "open": true, "role": "Platschef", "line": 12}' | byggmote correct add "<meeting folder>"
    byggmote correct remove "<meeting folder>" 5.4.2        and `restore` puts it back
    byggmote correct check "<meeting folder>" 5.4.1 1       the amount is read against the recording and right
    byggmote correct attend "<meeting folder>" @sara-nyberg was there and said nothing

- A point a person changes keeps what the model wrote (`proposed`), one a person writes is marked `added`, and one
  taken out is kept in the protocol's `removed`. What is a person's can always be told from what is a model's.
- A point's number is its name. A removed point leaves its number unused, and a point that is added, or moved to
  another heading, takes the next number there.
- An earlier meeting's open point is followed up or closed, not rewritten or removed: its text is that meeting's.
- A decision or a note is never left open, and only what stays open has a Roll and a day.
- An amount check stays while its amount is in the text. An amount a person writes is the person's.
- A protocol a later meeting builds on is not corrected, and a corrected protocol is not written again by a model
  without `protocol --discard`.
- Naming a speaker sets who was there in a draft protocol, so nothing has to be written again for that.

### Stommen's Projekt

Byggmöte is to have no projects of its own: a Projekt, its Roller and the Kontakter who hold them are Stommen's.
The engine takes one Projekt as Stommen has it, and Stommen wins:

    echo '{"project": {"id": "…", "name": "Kv. Eken kontorshus"},
           "roles": [{"id": "…", "name": "Platschef", "holderId": "…", "substituteId": null}],
           "contacts": [{"id": "…", "name": "Jonas Bergström", "organization": "Bergström Bygg AB", "email": "…"}]}' | byggmote stommen project

A Roll is its own thing, as in Stommen: it can be vacant and still be given a point, and one person can hold
several. A Kontakt becomes a person Byggmöte already knows when it can (the link from last time, else the e-mail,
else the name), since a person is one person across projects here. Someone who is no longer a Kontakt leaves the
project; the person and their meetings stay. The engine does not talk to Stommen: the app signs in and fetches.

The other way, `byggmote stommen minutes "<meeting folder>"` gives a meeting's protocol as Stommen is to take it
(Stommen's issue 253): each point with the Roll's id there, how many seconds into the recording it was said, the
line said there and who said it, and whether it stands as the model wrote it, was changed by a person or written by
one. It is refused while a check is left, and for a Roll that Stommen no longer has. Nothing sends it yet: Stommen
cannot take a protocol in, and the app has no button for it.

### The language model

Two run the same model, Qwen3.5 9B, locally:

- `qwen3.5-9b`: MLX, the Mac only, the default there.
- `qwen3.5-9b-gguf`: GGUF on llama.cpp's `llama-server`, the default on Windows and Linux and a choice on the Mac
  (`protocol --model qwen3.5-9b-gguf`). The engine starts the server for one answer and stops it: on 127.0.0.1 only,
  behind a key made for the run, never downloading. The server holds the answer to a JSON schema, so a heading, a
  kind, a Roll and an open point's number can only be ones there are.

`llama-server` comes from [llama.cpp's releases](https://github.com/ggml-org/llama.cpp/releases), one build per
platform. An app sets `BYGGMOTE_LLAMA_SERVER` to its own. A development checkout looks in `engine/bin/llama-*/`, then
on the path. Fetch the model with `byggmote models download qwen3.5-9b-gguf` (5.7 GB).

`protocol --prompt` prints the prompt and the schema, and `protocol --answer` takes any model's answer on stdin, so
the checks above apply whichever model wrote it.

### Tests

    uv run pytest

The fast tests cover the series, the numbering, the checks and how `llama-server` is started, asked and stopped
(against a stand-in), without any model. `BYGGMOTE_TEST_GGUF=model.gguf uv run pytest -m slow -n 0` runs the real
`llama-server` with that model. On GitHub both run on Windows and Linux for every push (`.github/workflows/test.yml`),
the real server with a small model: that shows the server works there, not how good a protocol is or how long the
large model takes. `tests/make_clip.sh` speaks
`tests/data/byggmote5.txt` into a two-minute recording with macOS's Swedish voice, for a run of the whole chain. The
engine that came from Tonband arrived without its tests.
