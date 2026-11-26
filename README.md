# Byggmöte

Records a construction meeting, transcribes it and writes the byggmötesprotokoll. Speech recognition, speaker
separation and the language model all run on the computer, so sound and text never leave it. What a person approves
goes on to Stommen as proposals.

**Status:** the engine runs as a CLI, from a recording to a numbered protocol, with either of two local language
models. Its tests and llama.cpp's server run on Windows and Linux on GitHub; a whole meeting has only been transcribed
on the Mac. The app is a first version: it shows a project's meetings, the agenda and a protocol with its transcript
and sound, records a meeting or takes a recording, names the speakers, and lets a person correct the protocol. It
signs in to Stommen as a person, fetches the person's Projekt with their Roller and Kontakter, and sends a protocol
there when the person asks. When the meeting is opened, and when the person asks, it reads from Stommen whether a sent
protocol is justerat there, and shows when, how and by whom; a justerat protocol is no longer corrected or sent from
the app. A correction is not tied to who is signed in. It installs on Windows, Linux and the Mac without developer
tools (Installing, below), not yet signed.
It also works with no Stommen at all: a project is made in the window (Projekt in the menu), with the people at its
meetings and their Roller, and its first mötesserie is started with it. A protocol is kept as `protocol.md` in the
meeting's folder, and the window can save it as a file or copy its text. Stommen is the thing to add later, from the
Stommen view. A first run (name, microphone, models, Stommen) and Inställningar (name, where meetings are kept, microphone, Recognise Voices,
open at login, models, licences) are in the app; the app keeps them in its own folder (`settings.json`). Still to build:
the phone recorder.

Where the engine comes from and what the models' licences ask: `NOTICE.md`.

## Installing

An installer carries all the app needs: the engine with its own Python, `ffmpeg` and `ffprobe`, and llama.cpp's
`llama-server` on Windows and Linux. Nothing is expected on the computer's path. The models are not in it: the first
run fetches them (about 7 GB, 9 GB on the Mac, one progress bar, Modeller under Inställningar later), and from then on the app works
without internet.

Download from the repo's releases:

| Computer                                 | File                                              |
| ---------------------------------------- | ------------------------------------------------- |
| Windows 10 or 11, x64                    | `Byggmote-<version>-win-x64.exe`                  |
| Ubuntu 22.04, Debian 12 or later, x64    | `Byggmote-<version>-linux-amd64.deb`, or the `.AppImage` for other distributions |
| Mac with Apple silicon, macOS 12 or later | `Byggmote-<version>-mac-arm64.dmg`               |

- **Windows.** Run the file and choose for whom. For IT, silently: `Byggmote-<version>-win-x64.exe /S /allusers`
  installs for everyone in `C:\Program Files\Byggmote`, `/S` alone for the person running it, and `/D=<folder>` (last)
  picks the folder: give it a folder of its own, since the uninstaller removes that whole folder with everything in
  it. Files and folders are named `Byggmote`, without the ö, so a script need not quote it; the
  name a person reads is Byggmöte. Uninstall in Settings, Apps, or silently:
  `"C:\Program Files\Byggmote\Uninstall Byggmote.exe" /S /allusers`.
- **Linux.** `sudo apt install ./Byggmote-<version>-linux-amd64.deb`, and `sudo apt remove byggmote` to uninstall. The
  AppImage runs as it is (`chmod +x`), and is uninstalled by removing the file.
- **Mac.** Open the `.dmg` and drag Byggmöte to Program. Uninstall by moving it to the trash. There is no `.pkg`, so
  a script installs it from the disk image:

      hdiutil attach -nobrowse -quiet -mountpoint /Volumes/Byggmote Byggmote-<version>-mac-arm64.dmg
      sudo cp -R /Volumes/Byggmote/Byggmote.app /Applications/
      hdiutil detach -quiet /Volumes/Byggmote

  and removes it with `sudo rm -rf /Applications/Byggmote.app`.

An uninstall removes the program and nothing else. The meetings stay in `Documents/Byggmöte` (or the folder chosen
under Inställningar), the settings in the app's own folder (`%APPDATA%\Byggmote`, `~/.config/Byggmote`,
`~/Library/Application Support/Byggmote`) and the models in `~/.cache/huggingface`. Removing those is a choice made by
hand.

### What computer it needs

| | Records and transcribes | Writes the protocol |
| --- | --- | --- |
| Memory | 8 GB | 16 GB |
| Disk | up to 2 GB for the app and 1.4 GB for speech and speakers (3.3 GB on the Mac) | 5.7 GB more for the language model (6 GB on the Mac) |
| Graphics card | not used on Windows and Linux, the CPU does it all | not used on Windows and Linux; on the Mac MLX uses Apple silicon's |

The 16 GB is what the engine asks of Qwen3.5 9B (`min_ram_gb` in `models.py`). On a computer with less, the models step
says plainly that the computer is too small to write a protocol, and when the disk has too little room for the models.
**Not measured yet:** how long a protocol takes, and whether 8 GB really carries an hour's meeting. That needs a
person to run a recorded hour, from the installed app, on a five-year-old laptop with 8 GB, on a 16 GB laptop without
a graphics card, and on a clean Windows and a clean Linux computer, and to write the times in this table.

### Building the installers

`.github/workflows/release.yml` builds all three from a tag `v*` and puts them on a draft release; a pull request that
changes how they are made builds them too, unsigned and without any of the repo's secrets. On each runner it installs
the result silently, runs the installed engine with nothing of the runner's on its path
(`app/scripts/smoke-installed.sh`: Python, the model list, `ffmpeg` and `ffprobe` reading a recording,
`llama-server`), uninstalls it silently and checks that the meetings folder the installed engine uses by default
(`Documents/Byggmöte`), with a project it made there, is as it was (`app/scripts/meetings-kept.sh`). On the Mac it
installs from the disk image with the script above. It does not run a meeting through the installed app: that
needs the models and a person to judge the protocol.

On a computer of one's own, from `app/`: `./scripts/bundle-engine.sh`, then `npm run dist` (the installer for that
system, in `app/dist/`). The bundle script pins every build it fetches by its checksum.

### Signing

Without signing, a company laptop will often refuse the file, and a person's own computer warns. Neither is done yet.
The workflow signs as soon as the secrets are in the repo:

- **Mac: not signed or notarised** (ad hoc only, which Apple silicon needs to start it). The Mac then says the app
  cannot be opened, and only right-click, Öppna gets past it. Missing: membership of the Apple Developer Program (99 USD
  a year, for the company), a Developer ID Application certificate from it, and the secrets `MAC_CSC_LINK` (the
  certificate as base64 `.p12`), `MAC_CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` and `APPLE_TEAM_ID`.
  electron-builder then signs and notarises.
- **Windows: not signed.** SmartScreen says "Windows skyddade datorn", and AppLocker or Smart App Control blocks it.
  Missing: a code signing certificate. Since 2023 a certificate authority only issues them on a hardware key or in a
  cloud HSM, so a `.pfx` in a secret (`WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD`, which the workflow takes) only works with
  an older one. The likely way is Microsoft's Azure Artifact Signing (from about 10 USD a month; check that it takes a
  Swedish company first), wired in with electron-builder's `win.azureSignOptions`; an OV certificate in a cloud HSM costs
  about 250 to 500 USD a year.
- **The Mac's speaker model.** pyannote community-1 is gated on Hugging Face but CC BY 4.0, so a copy sits unmodified
  on this repo's release `models-pyannote-community-1`, with its attribution. The Mac build fetches it from there and
  checks its SHA-256 (`bundle-engine.sh`); no token is needed. Windows and Linux use other speaker models.

## The app

Electron with Svelte 5, in `app/`. It has no data of its own: every view is what the engine's commands answer, and the
window reaches the computer only through the calls in `app/src/shared/types.ts`.

    cd app
    npm install
    npm run dev

It uses the engine of the checkout (`engine/.venv`), so install that first, or name another with `BYGGMOTE_ENGINE`.
Start it from a terminal: the engine needs `ffmpeg` on the path. Projects are made in the app (Projekt), or come from Stommen when the
person signs in there; a project from Stommen is Stommen's, and its people and Roller are read, not changed, in the app.

The window keeps to the computer's conventions. Its commands are in the application menu (`app/src/main/menu.ts`: the
Mac's menu bar, the window's own menu bar on Windows and Linux), each with a shortcut, and a choice there reaches the
window as a `Command`; what cannot run now is greyed out. On the Mac the window has no title bar of its own, and the
sidebar and the toolbar reach its top. The sidebar is the project's library: its overview (the next meeting, what is
open, the meetings, who is in it), the open points as a list of their own, each mötesserie's agenda, and the meetings.
Text, controls and rows have the Mac's measures or Windows' (`data-platform` in `app.css`); `BYGGMOTE_PLATFORM=win32`
shows Windows' on a Mac. Inställningar is a window of its own (⌘, / Ctrl+,), with the connection to Stommen as one of its tabs; what is
changed there the main window reads again. The palette (⌘K / Ctrl+K) runs a command or opens a meeting, an open point
or another project from a few letters. A meeting is recorded in a small window of its own that stays over other programs
(`app/src/main/recording.ts`, `views/RecordWindow.svelte`), with an icon beside the clock that has its commands, and
shortcuts that work in any program (⌃⌥N for the next heading, ⌃⌥1 to 4 for a mark, ⌃⌥P to pause; Alt+Shift with the
same keys on Windows and Linux). The main window is free meanwhile, and writes the recording out when the meeting is
ended. A recording is written out behind the window: it is listed in the sidebar with the step it is
at, the Dock's icon or the taskbar's button shows that work goes on, several wait their turn, and one that failed
stays in the list until it has been looked at. A protocol is a document in the window: an outline of its headings, the page, the transcript
beside it (it can be put away) and the recording under both, with what is done to it in the toolbar and in the
Protokoll and Arkiv menus (Ny punkt, Nästa att kontrollera, Spara som, Skicka till Stommen).

    npm run check     the types, main process and views
    npm test          builds the app and drives it against a knowledge base the engine writes (no model runs)

The tests run the window hidden (`BYGGMOTE_HIDDEN=1`), so a run does not take the screen and a click from whoever
sits at the computer cannot land in it. They also show the engine folders with no models in them: a test that asks
for a protocol to be written, by mistake or because an earlier test failed and the app started over, gets an error
and not minutes of a language model. Recording from a microphone to a written protocol is not in them: it needs the
models and several minutes, and has been run by hand with a sound clip played into the app as its microphone.

### Word and PDF

A protocol is saved as Word (`.docx`), PDF or Markdown from its page (the "Spara som" menu), to send as it
is or to open and edit. Both are made from `protocol.md`, so the headings, numbers and points are the window's own, and
`app/tests/export.spec.ts` compares them. Neither needs Word: the `.docx` is written by the `docx` library and the PDF
is printed by the app's own hidden window, so it is the same on Windows, Linux and Mac.

A Projekt can give the file its look: put `header.txt` (one line) and `logo.png`, `logo.jpg` or `logo.jpeg` in
`mallar/<project id>/` in the folder where Byggmöte keeps its projects (Inställningar shows it). The header and logo
go at the top of the Word file's every page and of the PDF's first. Without them the file is plain. The consent line and
the justering line are not kept anywhere yet: `closingLines` in `app/src/main/index.ts` is where they go, and both files
then end with them.

Teams meeting notes (and Copilot's recap) summarise a call for the people in it. A Byggmöte protocol is numbered by
heading, gives each point a Roll and a date, carries open points over from the earlier meeting, and every point points
at the sentence in the recording. Sent on to Stommen, a point becomes an ÄTA, a risk or a decision there with that trail.
The file is for those who work in Word and Outlook; the lines to Stommen are why to record here.

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
- What goes to Stommen is the sign-in and, when the person presses "Skicka till Stommen" on a protocol and says
  yes to what is listed, that protocol: its points, and for each how far into the recording it was said, the line
  said there and who said it. Sound and the rest of the transcript never go. A protocol with a check left is not
  sent, the same protocol sent twice is one send (its digest is the `Idempotency-Key`), and one changed after it was
  sent says so and goes again as a later version.
- The requests are made with Node's `http` and `https`, with the headers the app sets and no others. Node's `fetch`
  adds `sec-fetch-mode`, and Stommen then takes the sign-in for a browser's and refuses it for having no Origin.
- An account with two-factor sign-in is told Byggmöte cannot do that yet (Stommen's phone app cannot either).
- A Projekt that is gone from Stommen, or that the person no longer sees there, stays here with its meetings.

`tests/stommen.spec.ts` runs all of this against a stand-in for Stommen on the computer. The tests give the app a
folder of its own to keep things in (`BYGGMOTE_USER_DATA`) and no keychain (`BYGGMOTE_NO_KEYCHAIN=1`), so a run puts
nothing in the keychain of whoever runs it. The keychain path is checked by hand on the Mac only. Against a real
Stommen (a local one, with a database made for the trial) the sign-in, the fetch and the sign-out are checked by hand
once: that is where the `fetch` problem above showed, which the stand-in had not caught. So is sending: a protocol
went from the app into Stommen with its points, the seconds into the recording and the Roller, and again as a second
version after a correction.

An engine the app started does not outlive it: quitting stops them all, also one that is writing a protocol. That
is checked by hand on the Mac only.

The views follow the sketch at https://claude.ai/artifact/W2NsCiByVoWE7AUV4rGUMZ and use Stommen's design tokens.

## The engine

Python, installed with [uv](https://docs.astral.sh/uv/). It needs `ffmpeg` on the path.

    cd engine
    uv sync
    uv run byggmote models

Speech recognition and the language model download from Hugging Face on first use (`byggmote models download`). The
speaker model on the Mac, pyannote community-1, is gated there: take it from this repo's release `models-pyannote-community-1`
and unpack it into `engine/models/` once.
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

The other way, `byggmote stommen minutes "<meeting folder>"` gives a meeting's protocol as Stommen takes it
(`POST /api/mobile/v1/projects/{id}/minutes` there): each point with the Roll's id there, how many seconds into the recording it was said, the
line said there and who said it, and whether it stands as the model wrote it, was changed by a person or written by
one. It is refused while a check is left, and for a Roll that Stommen no longer has. The app sends it and tells the
engine what Stommen answered (`byggmote stommen sent`), so a meeting's detail can say when its protocol was sent and
whether it has changed since.

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
