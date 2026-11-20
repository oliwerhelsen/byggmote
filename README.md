# Byggmöte

Records a construction meeting, transcribes it and writes the byggmötesprotokoll. Speech recognition, speaker
separation and the language model all run on the computer, so sound and text never leave it. What a person approves
goes on to Stommen as proposals.

**Status:** the engine runs as a CLI on the Mac, from a recording to a numbered protocol. Still to build: the Electron
app, the connection to Stommen, a local language model for Windows and Linux, and the phone recorder.

Where the engine comes from and what the models' licences ask: `NOTICE.md`.

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

### Another language model

On Windows and Linux there is no local language model yet. `protocol --prompt` prints the prompt and
`protocol --answer` takes any model's answer on stdin, so the checks above apply whichever model wrote it.

### Tests

    uv run pytest

The fast tests cover the series, the numbering and the checks, without any model. `tests/make_clip.sh` speaks
`tests/data/byggmote5.txt` into a two-minute recording with macOS's Swedish voice, for a run of the whole chain. The
engine that came from Tonband arrived without its tests.
