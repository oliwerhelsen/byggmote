import argparse
import contextlib
import json
import sys
import traceback
from pathlib import Path

from . import ArgError, areas, meeting, people, scratch, short_error


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _stdin():
    """The fields on stdin (SPEC.md, Editing the knowledge base)."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        raise ArgError(f"fields on stdin: {e}") from None


def summarize(model: str) -> int:
    """`byggmote summarize`: the answer only once the model is done, so a stop or an error leaves no half answer."""
    from .models import REGISTRY, adapter, downloaded
    e = next((e for e in REGISTRY if e["id"] == model and e["type"] == "llm"), None)
    prompt = sys.stdin.read()
    if not e:
        _print({"error": f"unknown language model: {model}"})
        return 2
    if not prompt.strip():
        _print({"error": "empty prompt"})
        return 2
    if not downloaded(e):
        _print({"error": f"model not downloaded: {model}"})
        return 1
    try:
        with contextlib.redirect_stdout(sys.stderr):  # model libraries print
            m = adapter(e)
            m.load()
            text = m.summarize(prompt)
    except Exception as x:
        traceback.print_exc()
        _print({"error": short_error(x)})
        return 1
    sys.stdout.write(text)
    return 0


def protocol(a) -> int:
    """`byggmote protocol`: the prompt, another model's answer made the protocol, or the local model from start to end."""
    from . import protocol as pr
    d = Path(a.dir).expanduser()
    if a.prompt and a.answer:
        raise ArgError("--prompt or --answer, not both")
    if a.prompt:
        _print(pr.request(d, a.series, a.no))
        return 0
    if a.answer:
        _print(pr.answer(d, a.series, sys.stdin.read(), a.no, a.model, a.discard))
        return 0
    from .models import REGISTRY, adapter, downloaded
    from .run import Stopped, on_stop
    e = next((e for e in REGISTRY if e["type"] == "llm" and a.model in (None, e["id"])), None)
    if not e:
        raise ArgError("no local language model here: --prompt gives the prompt, --answer takes another model's answer")
    if not downloaded(e):
        raise ValueError(f"model not downloaded: {e['id']}")
    req = pr.request(d, a.series, a.no)
    if not a.discard and (had := pr.corrections(pr.load(d) or {})):  # before the model has worked a minute for nothing
        raise ArgError(f"the protocol has {had} corrections by a person: --discard writes over them")
    try:
        with on_stop(), contextlib.redirect_stdout(sys.stderr):  # model libraries print
            m = adapter(e)
            m.load()
            text = m.summarize(req["prompt"], req["schema"])
    except Stopped:
        return 1
    _print(pr.answer(d, a.series, text, a.no, e["id"], a.discard))
    return 0


def correct(a) -> dict | list | None:
    """`byggmote correct`: what a person sets right in a protocol."""
    from . import correct as co
    d = Path(a.dir).expanduser()
    if a.op == "change":
        return co.change(d, a.no, _stdin())
    if a.op == "add":
        return co.add(d, _stdin())
    if a.op == "remove":
        return co.remove(d, a.no)
    if a.op == "restore":
        return co.restore(d, a.no)
    if a.op == "check":
        return co.check(d, a.no, a.n, a.undo)
    if a.op == "attend":
        return co.attend(d, a.person, a.remove)
    return co.attendees(d)


class Parser(argparse.ArgumentParser):
    """Usage errors as the SPEC's JSON error, exit 2; the usage text goes to stderr."""
    def error(self, message):
        self.print_usage(sys.stderr)
        if self.prog.endswith(" run"):
            print(json.dumps({"event": "error", "step": "args", "message": message}))
        else:
            _print({"error": message})
        sys.exit(2)


def main(argv=None) -> int:
    p = Parser(prog="byggmote", description="Local meeting transcription engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("probe", help="inspect a file")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("run", help="transcribe a file (JSON lines on stdout)")
    s.add_argument("file")
    s.add_argument("--area", required=True)
    s.add_argument("--lang", choices=["sv", "en"])
    s.add_argument("--title")
    s.add_argument("--track", action="append", metavar="N=skip|split|NAME")
    s.add_argument("--speakers", metavar="MIN-MAX")
    s.add_argument("--out", metavar="DIR")
    s.add_argument("--attendee", action="append", default=[], metavar="NAME <EMAIL>")
    s.add_argument("--no-vocabulary", action="store_true", help="the plain decode, without the area's names and terms")
    s = sub.add_parser("rename", help="rename speakers")
    s.add_argument("dir")
    s.add_argument("pairs", nargs="+", metavar="OLD=NEW")
    s = sub.add_parser("name", help="name a speaker as the user does: a new name creates the person, who joins the area (JSON)")
    s.add_argument("dir")
    s.add_argument("speaker")
    s.add_argument("new", nargs="?", metavar="NEW", help="@id, another speaker's name or a name")
    s.add_argument("--email", help="for a new person: the calendar attendee's email")
    s.add_argument("--remove", action="store_true", help="Remove Name: back to Talare N, a person the meeting brought goes")
    s = sub.add_parser("reassign", help="move a segment to another speaker")
    s.add_argument("dir")
    s.add_argument("segment", type=int)
    s.add_argument("speaker")
    s = sub.add_parser("edit", help="set a segment's text (the words stay as heard)")
    s.add_argument("dir")
    s.add_argument("segment", type=int)
    s.add_argument("text")
    s = sub.add_parser("move", help="move a meeting to another area")
    s.add_argument("dir")
    s.add_argument("area")
    s = sub.add_parser("people", help="add or change a person (fields as JSON on stdin), merge or delete people across all meetings")
    pp = s.add_subparsers(dest="op", required=True)
    pp.add_parser("add", help="a new person from {\"name\", \"short\", \"note\", \"email\", \"all_areas\", \"areas\", \"heard\"}")
    x = pp.add_parser("set", help="change the fields given: name, short, note, email, all_areas, areas, heard")
    x.add_argument("id")
    x = pp.add_parser("merge", help="REMOVED becomes KEPT everywhere")
    x.add_argument("removed")
    x.add_argument("kept")
    x = pp.add_parser("delete", help="delete a person no meeting links (--force unlinks them)")
    x.add_argument("id")
    x.add_argument("--force", action="store_true")
    x = pp.add_parser("forget-voice", help="remove the person's voice prints from every meeting; names stay")
    x.add_argument("id")
    s = sub.add_parser("areas", help="add, change or delete an area: the fields as JSON on stdin (JSON)")
    pp = s.add_subparsers(dest="op", required=True)
    pp.add_parser("add", help="a new project from {\"name\", \"lang\", \"short\", \"server\"}")
    x = pp.add_parser("set", help="change the fields given: name, short, lang, people, summaries, context, move")
    x.add_argument("id")
    pp.add_parser("notes", help="the notes folder, where each project can keep its minutes, from {\"folder\"}; null removes it")
    x = pp.add_parser("delete", help="the area leaves areas.json; its meetings' folders stay")
    x.add_argument("id")
    x = pp.add_parser("share", help="move the project's meetings into a folder the team shares, as <FOLDER>/<name>")
    x.add_argument("id")
    x.add_argument("folder")
    x = pp.add_parser("join", help="add the shared projects in FOLDER (it or its subfolders)")
    x.add_argument("folder")
    s = sub.add_parser("project", help="a server project's knowledge: what a meeting taught, and the server's into the project (JSON)")
    pp = s.add_subparsers(dest="op", required=True)
    x = pp.add_parser("taught", help="the people and terms the meeting in DIR taught its server project, as the server takes them")
    x.add_argument("dir")
    x = pp.add_parser("sync", help="the server's knowledge on stdin into the server project AREA; the server wins there")
    x.add_argument("area")
    s = sub.add_parser("voices", help="Recognise Voices: on, or off (no new voice prints, no matches) (JSON)")
    s.add_argument("state", choices=["on", "off"])
    s = sub.add_parser("me", help="set who I am: @id or a full name (created if new)")
    s.add_argument("ref", metavar="@ID|NAME")
    s = sub.add_parser("folder", help="make PATH the app's folder: the knowledge base moves there, or is used if it has one")
    s.add_argument("path", type=Path)
    s = sub.add_parser("summarize", help="the local model answers: the whole prompt on stdin, its answer on stdout")
    s.add_argument("--model", required=True, metavar="ID")
    s = sub.add_parser("title", help="set the meeting's title")
    s.add_argument("dir")
    s.add_argument("text")
    s = sub.add_parser("status", help="set meeting status")
    s.add_argument("dir")
    s.add_argument("status", choices=meeting.STATUSES)
    s = sub.add_parser("render", help="rewrite transcript.txt with the current people and roles")
    s.add_argument("dirs", nargs="+", metavar="DIR")
    s = sub.add_parser("terms", help="names and terms for context-aware dictation")
    tt = s.add_subparsers(dest="op", required=True)
    x = tt.add_parser("suggest", help="what a language model suggests from a meeting: its prompt, or its answer as proposals (JSON)")
    x.add_argument("--meeting", metavar="DIR", type=Path, required=True, help="the meeting: its minutes, edited lines and transcript")
    x.add_argument("--lang", choices=["sv", "en"], help="language of the reasons (default: the area's)")
    x.add_argument("--skip", action="append", default=[], metavar="TERM", help="a term turned down before (repeatable)")
    x.add_argument("--prompt", action="store_true", help="the system prompt, prompt and schema for the model")
    x.add_argument("--budget", type=int, metavar="N", help="with --prompt: characters of evidence")
    x.add_argument("--answer", action="store_true", help="the model's answer on stdin, cleaned into proposals")
    tt.add_parser("add", help="a line from {\"term\", \"heard\", \"area\"} on stdin; a line with the term in that place is joined")
    tt.add_parser("set", help="change the line {\"was\": {\"term\", \"area\"}} on stdin names: term, heard, area")
    tt.add_parser("delete", help="remove the line {\"term\", \"area\"} on stdin names")
    s = sub.add_parser("summary", help="what minutes edited after the app wrote them teach (JSON)")
    tt = s.add_subparsers(dest="op", required=True)
    x = tt.add_parser("terms", help="words swapped in the meeting's minutes, as term proposals")
    x.add_argument("dir")
    x.add_argument("--lang", choices=["sv", "en"], help="language of the reasons (default: the area's)")
    x.add_argument("--skip", action="append", default=[], metavar="TERM", help="a term turned down before (repeatable)")
    s = sub.add_parser("learn", help="what the app learns by itself from a meeting, its undo and correction (JSON)")
    tt = s.add_subparsers(dest="op", required=True)
    x = tt.add_parser("apply", help="apply the meeting's proposals on stdin that the app learns by itself; print them and the rest")
    x.add_argument("dir")
    x.add_argument("--all", action="store_true", help="also a new person and the meeting's voice matches (the app)")
    x = tt.add_parser("undo", help="take back what the meeting applied under KEY (term:cietrade)")
    x.add_argument("dir")
    x.add_argument("key")
    x = tt.add_parser("correct", help="respell the term or person the meeting applied under KEY (term:ekmann)")
    x.add_argument("dir")
    x.add_argument("key")
    x.add_argument("spelling")
    s = sub.add_parser("serve", help="resident engine: JSON requests on stdin, events on stdout")
    s.add_argument("--langs", default="sv,en", metavar="sv,en", help="preload these ASR languages (\"\": none)")
    sub.add_parser("projects", help="the projects with their people, roles and series (JSON)")
    s = sub.add_parser("meetings", help="a project's meetings, the latest first (JSON)")
    s.add_argument("area")
    s = sub.add_parser("meeting", help="one meeting: its transcript's lines and its protocol (JSON)")
    s.add_argument("dir")
    s = sub.add_parser("series", help="a project's meeting series and their headings (JSON)")
    pp = s.add_subparsers(dest="op", required=True)
    x = pp.add_parser("start", help="a new series in project AREA from {\"name\", \"headings\"} on stdin; without headings, a byggmöte's")
    x.add_argument("area")
    x = pp.add_parser("heading", help="{\"no\", \"name\", \"hint\"} on stdin renames a heading; without no, a new one goes last")
    x.add_argument("area")
    x.add_argument("series")
    x = pp.add_parser("show", help="the project's series")
    x.add_argument("area")
    s = sub.add_parser("agenda", help="the next meeting's agenda: the headings and the points still open under them (JSON)")
    s.add_argument("area")
    s.add_argument("series")
    s = sub.add_parser("protocol", help="write the meeting's protocol with the local model: protocol.json and protocol.md (JSON)")
    s.add_argument("dir")
    s.add_argument("--series", required=True, metavar="ID")
    s.add_argument("--no", type=int, metavar="N", help="the meeting's number in the series (default: its own, else the next)")
    s.add_argument("--model", metavar="ID")
    s.add_argument("--prompt", action="store_true", help="only the prompt and the answer's JSON schema, for another model to answer")
    s.add_argument("--answer", action="store_true", help="another model's answer on stdin becomes the protocol")
    s.add_argument("--discard", action="store_true", help="write over a protocol a person has corrected")
    s = sub.add_parser("correct", help="what a person sets right in a meeting's protocol; fields as JSON on stdin (JSON)")
    pp = s.add_subparsers(dest="op", required=True)
    x = pp.add_parser("change", help="set text, kind, heading, role, due, open of point NO; follow, role, due, open of an earlier meeting's")
    x.add_argument("dir")
    x.add_argument("no")
    x = pp.add_parser("add", help="a point from {\"heading\", \"kind\", \"text\", \"open\", \"role\", \"due\", \"line\"}")
    x.add_argument("dir")
    x = pp.add_parser("remove", help="point NO out of the protocol; it is kept, to put back")
    x.add_argument("dir")
    x.add_argument("no")
    x = pp.add_parser("restore", help="a removed point back")
    x.add_argument("dir")
    x.add_argument("no")
    x = pp.add_parser("check", help="check N (from 1) of point NO is read against the recording and right")
    x.add_argument("dir")
    x.add_argument("no")
    x.add_argument("n", type=int)
    x.add_argument("--undo", action="store_true")
    x = pp.add_parser("attend", help="a person of the project was there and said nothing")
    x.add_argument("dir")
    x.add_argument("person", metavar="@ID")
    x.add_argument("--remove", action="store_true", help="not there after all")
    x = pp.add_parser("attendees", help="who was there, again from the meeting's speakers")
    x.add_argument("dir")
    s = sub.add_parser("stommen", help="what Stommen has, into the knowledge base (JSON)")
    pp = s.add_subparsers(dest="op", required=True)
    pp.add_parser("project", help="one Projekt from {\"project\": {\"id\", \"name\"}, \"roles\", \"contacts\"} on stdin: Stommen wins")
    x = pp.add_parser("minutes", help="the meeting's protocol as Stommen takes it, for the app to send; refused while a check is left")
    x.add_argument("dir")
    sub.add_parser("version", help="engine and protocol version (JSON)")
    s = sub.add_parser("models", help="list models, download them ahead of first use (JSON lines), or discard a stopped download")
    s.add_argument("--json", action="store_true")
    s.add_argument("action", nargs="?", choices=["download", "discard"])
    s.add_argument("ids", nargs="*", metavar="ID", help="download these (default: every default model), or discard their partial files")
    a = p.parse_args(argv)

    if a.cmd == "version":
        from . import PROTOCOL, __version__
        print(json.dumps({"version": __version__, "protocol": PROTOCOL}))
        return 0
    if a.cmd == "run":
        from .run import on_stop, run
        with on_stop(), scratch():
            return run(a)
    if a.cmd == "serve":
        from .serve import serve
        return serve(a)
    if a.cmd == "models" and a.action == "download":
        from .models import download
        from .run import Emitter
        out, sys.stdout = sys.stdout, sys.stderr  # model libraries print; keep stdout for events
        try:
            return download(a.ids, Emitter(out))
        finally:
            sys.stdout = out
    if a.cmd == "models" and a.action == "discard":
        from .models import discard
        try:
            _print({"discarded": discard(a.ids)})
            return 0
        except ValueError as e:
            _print({"error": str(e)})
            return 2
    if a.cmd == "summarize":
        from .run import Stopped, on_stop
        try:
            with on_stop():
                return summarize(a.model)
        except Stopped:
            return 1
    try:
        if a.cmd != "folder":  # it may be the way out of a missing folder
            try:
                areas.load()  # creates or migrates the config; the app runs `byggmote models` for this
            except (areas.FolderMissing, PermissionError):
                if a.cmd != "models":  # the models are the engine's: first run says what keeps the folder out on its folder step
                    raise
        if a.cmd == "probe":
            from .probe import probe
            info = probe(Path(a.file), areas.load().get("me"))
            if a.json:
                _print(info)
            else:
                print(f"{info['source']} {info['container']} {meeting.clock(info['duration'])} {info['size'] / 1e6:.0f} MB")
                for t in info["tracks"]:
                    print(f"  {t['id']} {t['name'] or '-'} {t['channels']}ch peak {t['peak_db']} dB"
                          f" -> {info['suggested'][t['id']]}")
        elif a.cmd == "models":
            from .models import listing
            ms = listing()
            if a.json:
                _print(ms)
            else:
                for x in ms:
                    print(f"{x['id']:22} {x['type']:8} {','.join(x['langs']) or '*':4} {x['size'] / 1e9:4.1f} GB"
                          f" {'ok' if x['downloaded'] else '-'}")
        elif a.cmd == "render":
            for d in a.dirs:
                meeting.write_transcript(Path(d), meeting.load(Path(d)))
        elif a.cmd == "people":
            if a.op in ("add", "set"):
                _print(people.add(_stdin()) if a.op == "add" else people.set_person(a.id, _stdin()))
            elif a.op == "merge":
                _print({"meetings": people.merge(a.removed, a.kept)})
            elif a.op == "forget-voice":
                from . import voice
                _print({"meetings": voice.forget(a.id)})
            else:
                with _locked():
                    _print({"meetings": people.delete(a.id, a.force)})
        elif a.cmd == "terms" and a.op == "suggest":
            from . import suggest
            if a.prompt == a.answer:
                raise ArgError("--prompt or --answer, one of them")
            if a.budget is not None and not a.prompt:
                raise ArgError("--budget goes with --prompt")
            d = a.meeting.expanduser()
            if a.prompt:
                _print(suggest.request(d, a.lang, a.skip, a.budget))
            else:
                try:
                    found = suggest.read(sys.stdin.read())
                except ValueError as e:  # the model's fault, not the run's: no proposals (#646)
                    print(e, file=sys.stderr)
                    found = []
                _print({"proposals": suggest.answer(d, found, a.skip)})
        elif a.cmd == "terms":
            from . import terms
            _print({"add": terms.add, "set": terms.set_term, "delete": terms.delete}[a.op](_stdin()))
        elif a.cmd == "summary":
            from . import summary
            _print({"proposals": summary.terms(Path(a.dir).expanduser(), a.lang, a.skip)})
        elif a.cmd == "learn":
            from . import learn
            d = Path(a.dir).expanduser()
            if a.op == "undo":
                _print({"undone": learn.undo(d, a.key)})
            elif a.op == "correct":
                if not a.spelling.strip() or "=" in a.spelling:
                    raise ArgError("SPELLING: expected text without =")
                _print({"corrected": learn.correct(d, a.key, a.spelling)})
            else:
                try:
                    given = json.loads(sys.stdin.read())
                except json.JSONDecodeError as e:
                    raise ArgError(f"proposals on stdin: {e}") from None
                given = given.get("proposals") if isinstance(given, dict) else given
                if not isinstance(given, list):
                    raise ArgError("proposals on stdin: expected {\"proposals\": [...]}")
                _print(learn.apply(d, given, a.all))
        elif a.cmd == "name":
            from . import naming
            d = Path(a.dir).expanduser()
            if a.remove:
                if a.new is not None or a.email:
                    raise ArgError("--remove takes no NEW or --email")
                done = naming.remove(d, a.speaker)
            else:
                if a.new is None:
                    raise ArgError("expected NEW or --remove")
                done = naming.name(d, a.speaker, a.new, a.email)
            try:  # a draft protocol says who was there: now with the name. The naming is done whatever comes of this.
                from . import correct as co
                co.attendees(d)
            except (OSError, ValueError):
                pass
            _print(done)
        elif a.cmd == "areas":
            if a.op == "delete":
                _print(areas.delete(a.id))
            elif a.op == "share":
                _print(areas.share(a.id, a.folder))
            elif a.op == "join":
                _print(areas.join(a.folder))
            elif a.op == "notes":
                _print(areas.set_notes(_stdin()))
            else:
                _print(areas.add(_stdin()) if a.op == "add" else areas.set_area(a.id, _stdin()))
        elif a.cmd == "project":
            from . import project
            if a.op == "taught":
                _print(project.taught(Path(a.dir).expanduser()))
            else:
                _print(project.sync(a.area, _stdin()))
        elif a.cmd == "voices":
            from . import voice
            _print(voice.turn(a.state == "on"))
        elif a.cmd == "me":
            with _locked():
                _print(people.set_me(a.ref))
        elif a.cmd == "folder":
            from . import knowledge
            to = knowledge.move_to(a.path)
            _print({"folder": str(to)})
        elif a.cmd in ("projects", "meetings", "meeting"):
            from . import overview
            _print(overview.projects() if a.cmd == "projects" else overview.meetings(a.area) if a.cmd == "meetings"
                   else overview.detail(Path(a.dir)))
        elif a.cmd == "series":
            from . import series
            if a.op == "start":
                _print(series.start(a.area, _stdin()))
            elif a.op == "heading":
                _print(series.heading(a.area, a.series, _stdin()))
            else:
                _print(series.load(areas.get_known(areas.load(), a.area)))
        elif a.cmd == "agenda":
            from . import series
            _print(series.agenda(a.area, a.series))
        elif a.cmd == "protocol":
            return protocol(a)
        elif a.cmd == "correct":
            _print(correct(a))
        elif a.cmd == "stommen":
            from . import stommen
            _print(stommen.take(_stdin()) if a.op == "project" else stommen.minutes(Path(a.dir)))
        elif a.cmd == "move":
            d = Path(a.dir).expanduser()
            with _locked():
                _print({"dir": str(meeting.move(d, meeting.load(d), a.area))})
        else:
            d = Path(a.dir).expanduser()
            with _locked():
                m = meeting.load(d)
                if a.cmd == "rename":
                    meeting.rename(m, a.pairs)
                elif a.cmd == "reassign":
                    meeting.reassign(m, a.segment, a.speaker)
                elif a.cmd == "edit":
                    meeting.edit(m, a.segment, a.text)
                elif a.cmd == "title":
                    meeting.set_title(m, a.text)
                else:
                    m["status"] = a.status
                meeting.save(d, m, transcript=a.cmd in ("rename", "reassign", "edit", "title"))
        return 0
    except ArgError as e:
        _print({"error": str(e)})
        return 2
    except people.InUse as e:
        _print({"error": str(e), "meetings": e.meetings})
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(repr(e), file=sys.stderr)
        _print({"error": short_error(e)})
        return 1
    except KeyError as e:
        _print({"error": f"missing field {e}"})
        return 1


def _locked():
    """The knowledge base's lock, as `learn` and `name` take it: a meeting edit read before another engine's write and saved after it
    would put back what that engine changed."""
    from . import knowledge
    return knowledge.locked(knowledge.folder())


def entry():
    """The `byggmote` command. UTF-8 in and out whatever the Windows code page, PYTHONUTF8 or not."""
    for s in (sys.stdin, sys.stdout, sys.stderr):
        if s:  # None without that handle (a windowless parent)
            s.reconfigure(encoding="utf-8")
    sys.exit(main())


if __name__ == "__main__":
    entry()
