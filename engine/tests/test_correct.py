import json

import pytest

from byggmote import ArgError, cli, correct, overview, protocol, series

from test_protocol import SAID, point, write

ATA = point(kind="decision", text="Beställaren godkänner ÄTA 14 till fast pris 86 500 kr.")
TODO = point(kind="todo", text="Underlag för mängdreglering skickas.", role="Platschef", due="2026-11-26",
             time="21:05", quote="Jag skickar underlaget för mängdregleringen")


def numbers(d) -> list[str]:
    return [x["no"] for x in protocol.load(d)["points"]]


def test_a_changed_point_keeps_what_the_model_wrote(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [TODO], no=3)
    x = correct.change(d, "3.4.1", {"text": "  Platschefen skickar underlag  för mängdreglering av schakt. ", "due": "2026-11-27"})
    assert (x["no"], x["text"], x["due"], x["role"]) == ("3.4.1", "Platschefen skickar underlag för mängdreglering av schakt.", "2026-11-27", "Platschef")
    assert x["proposed"] == {"text": "Underlag för mängdreglering skickas.", "kind": "todo", "heading": 4, "role": "Platschef",
                             "due": "2026-11-26", "open": True}
    again = correct.change(d, "3.4.1", {"kind": "question"})
    assert (again["kind"], again["proposed"]["text"], again["proposed"]["kind"]) == ("question", "Underlag för mängdreglering skickas.", "todo")
    assert "- **3.4.1** Fråga. Platschefen skickar underlag för mängdreglering av schakt. Ansvarig: Platschef. Senast 2026-11-27. [21:05]\n" \
        in (d / protocol.TEXT).read_text(encoding="utf-8")
    assert protocol.corrections(protocol.load(d)) == 1


def test_a_change_that_changes_nothing_is_no_correction(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [TODO], no=3)
    x = correct.change(d, "3.4.1", {"text": "Underlag för mängdreglering skickas.", "role": "platschef"})
    assert "edited" not in x and "proposed" not in x
    assert protocol.corrections(protocol.load(d)) == 0


def test_an_amount_check_stays_while_its_amount_is_in_the_text(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [ATA], no=3)
    assert [c["value"] for c in correct.change(d, "3.4.1", {"text": "ÄTA 14 beställs till fast pris 86 500 kr."})["checks"]] == ["86 500 kr"]
    assert correct.change(d, "3.4.1", {"text": "ÄTA 14 beställs till fast pris 68 500 kr."})["checks"] == []


def test_a_person_confirms_an_amount_and_can_take_it_back(project, held):
    aid, sid = project
    d = held("Byggmöte 3", SAID)
    write(d, sid, [ATA, point(heading=5, kind="question", text="Frågan skickas.", role="Konstruktören")], no=3)
    assert overview.meetings(aid)[0]["protocol"]["checks"] == 2
    assert "confirmed" in correct.check(d, "3.4.1", 1)["checks"][0]
    assert overview.meetings(aid)[0]["protocol"]["checks"] == 1
    assert "Kontrollera beloppet" not in (d / protocol.TEXT).read_text(encoding="utf-8")
    assert protocol.corrections(protocol.load(d)) == 1
    assert "confirmed" not in correct.check(d, "3.4.1", 1, undo=True)["checks"][0]
    assert "Kontrollera beloppet 86 500 kr." in (d / protocol.TEXT).read_text(encoding="utf-8")
    for no, n in (("3.5.1", 1), ("3.4.1", 2), ("3.4.1", 0)):  # a role is chosen, not confirmed; and no such check
        with pytest.raises(ArgError):
            correct.check(d, no, n)


def test_a_role_check_goes_when_a_person_has_chosen(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [point(heading=5, kind="question", text="Frågan skickas.", role="Konstruktören"),
                          point(heading=6, kind="question", text="Vem bekostar värmen?", role="Konstruktören")], no=3)
    with pytest.raises(ArgError):
        correct.change(d, "3.5.1", {"role": "Konstruktören"})
    assert protocol.load(d)["points"][0]["checks"] == [{"code": "role", "said": "Konstruktören"}]
    x = correct.change(d, "3.5.1", {"role": "beställarens ombud"})
    assert (x["role"], x["checks"]) == ("Beställarens ombud", [])
    none = correct.change(d, "3.6.1", {"role": None})  # nobody: a choice too, and nothing else changed
    assert (none["role"], none["checks"], "edited" in none) == (None, [], False)


def test_a_closed_point_asks_for_no_role(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [point(heading=5, kind="question", text="Frågan skickas.", role="Konstruktören")], no=3)
    assert correct.change(d, "3.5.1", {"open": False})["checks"] == []


def test_a_decision_is_not_left_open_and_a_closed_point_has_no_one_to_do_it(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [TODO], no=3)
    with pytest.raises(ArgError):
        correct.change(d, "3.4.1", {"kind": "decision", "open": True})
    x = correct.change(d, "3.4.1", {"kind": "decision"})
    assert (x["open"], x["role"], x["due"]) == (False, None, None)
    back = correct.change(d, "3.4.1", {"kind": "todo", "open": True, "role": "Platschef"})
    assert (back["open"], back["role"], back["due"]) == (True, "Platschef", None)
    for bad in ({"kind": "beslut"}, {"heading": 1}, {"heading": 99}, {"heading": True}, {"due": "fredag"}, {"text": " "},
                {"follow": "Klart."}, {"no": "3.4.9"}, "text"):
        with pytest.raises(ArgError):
            correct.change(d, "3.4.1", bad)
    with pytest.raises(ArgError):
        correct.change(d, "3.4.2", {"text": "Finns inte."})


def test_a_point_moved_to_another_heading_takes_the_next_number_there(project, held):
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [ATA, TODO, point(heading=5, text="Ritning K-20 saknas.")], no=3)
    assert correct.change(d, "3.4.1", {"heading": 5})["no"] == "3.5.2"
    assert numbers(d) == ["3.4.2", "3.5.1", "3.5.2"]


def test_a_person_adds_a_point_and_points_at_where_it_is_said(project, held):
    aid, sid = project
    d = held("Byggmöte 3", SAID)
    write(d, sid, [ATA], no=3)
    x = correct.add(d, {"heading": 4, "kind": "todo", "text": "Platschefen skickar underlag.", "open": True, "role": "Platschef",
                        "due": "2026-11-26", "line": 5})
    assert (x["no"], x["at"], x["line"], x["open"], x["role"], x["checks"]) == ("3.4.2", 1265.0, 5, True, "Platschef", [])
    assert "added" in x and "proposed" not in x
    note = correct.add(d, {"heading": 3, "kind": "note", "text": "Tidplanen hålls.", "role": "Platschef", "due": "2026-11-26"})
    assert (note["no"], note["at"], note["open"], note["role"], note["due"]) == ("3.3.1", None, False, None, None)
    assert numbers(d) == ["3.3.1", "3.4.1", "3.4.2"]
    assert [p["no"] for h in series.agenda(aid, sid)["headings"] for p in h["open"]] == ["3.4.2"]
    assert "- **3.3.1** Notering. Tidplanen hålls.\n" in (d / protocol.TEXT).read_text(encoding="utf-8")
    mine = correct.change(d, "3.4.2", {"text": "Platschefen skickar underlaget."})  # a person's own point has no proposal behind it
    assert "edited" in mine and "proposed" not in mine
    for bad in ({"heading": 4, "kind": "todo"}, {"heading": 1, "kind": "note", "text": "Här."}, {"kind": "note", "text": "Här."},
                {"heading": 4, "kind": "note", "text": "Här.", "line": 99}, {"heading": 4, "kind": "decision", "text": "Här.", "open": True}):
        with pytest.raises(ArgError):
            correct.add(d, bad)


def test_a_removed_point_is_off_the_agenda_keeps_its_number_and_can_be_put_back(project, held):
    aid, sid = project
    d = held("Byggmöte 3", SAID)
    write(d, sid, [ATA, TODO], no=3)
    assert correct.remove(d, "3.4.2") == {"removed": "3.4.2"}
    assert numbers(d) == ["3.4.1"]
    assert not any(h["open"] for h in series.agenda(aid, sid)["headings"])
    assert "3.4.2" not in (d / protocol.TEXT).read_text(encoding="utf-8")
    assert correct.add(d, {"heading": 4, "kind": "note", "text": "Betalningsplanen följs."})["no"] == "3.4.3"
    assert protocol.corrections(protocol.load(d)) == 2
    back = correct.restore(d, "3.4.2")
    assert (back["text"], "removed" in back) == ("Underlag för mängdreglering skickas.", False)
    assert numbers(d) == ["3.4.1", "3.4.2", "3.4.3"]
    assert [p["no"] for h in series.agenda(aid, sid)["headings"] for p in h["open"]] == ["3.4.2"]
    with pytest.raises(ArgError):
        correct.restore(d, "3.4.2")


def test_an_earlier_meetings_point_is_followed_up_or_closed_by_a_person(project, held):
    aid, sid = project
    write(held("Byggmöte 3", SAID), sid, [TODO], no=3)
    d = held("Byggmöte 4", SAID[:2])
    write(d, sid)  # the model did not find the point taken up
    x = correct.change(d, "3.4.1", {"follow": "Underlaget kom i tisdags.", "open": False})
    assert (x["raised"], x["follow"], x["open"], x["text"], x["role"]) == (True, "Underlaget kom i tisdags.", False, "Underlag för mängdreglering skickas.", "Platschef")
    assert x["proposed"] == {"follow": None, "role": "Platschef", "due": "2026-11-26", "open": True}
    assert "- **3.4.1** Att göra, avslutad från byggmöte 3. Underlag för mängdreglering skickas. Ansvarig: Platschef. Senast 2026-11-26.\n" \
        "  - På mötet: Underlaget kom i tisdags.\n" in (d / protocol.TEXT).read_text(encoding="utf-8")
    assert not any(h["open"] for h in series.agenda(aid, sid)["headings"])
    again = correct.change(d, "3.4.1", {"follow": "", "open": True, "due": "2026-12-03"})
    assert (again["raised"], again["follow"], again["due"]) == (False, None, "2026-12-03")
    assert series.agenda(aid, sid)["headings"][3]["open"][0]["due"] == "2026-12-03"
    for bad in ({"text": "Ny text."}, {"kind": "note"}, {"heading": 5}):
        with pytest.raises(ArgError):
            correct.change(d, "3.4.1", bad)
    with pytest.raises(ArgError):
        correct.remove(d, "3.4.1")


def test_a_protocol_a_later_meeting_builds_on_is_not_corrected(project, held):
    sid = project[1]
    first = held("Byggmöte 3", SAID)
    write(first, sid, [ATA, TODO], no=3)
    correct.remove(first, "3.4.1")
    write(held("Byggmöte 4", SAID), sid)
    for act in (lambda: correct.change(first, "3.4.2", {"open": False}), lambda: correct.add(first, {"heading": 4, "kind": "note", "text": "Här."}),
                lambda: correct.remove(first, "3.4.2"), lambda: correct.restore(first, "3.4.1")):
        with pytest.raises(ArgError, match="Byggmöte 4 builds on this protocol"):
            act()
    assert (overview.detail(first)["later"], overview.detail(first)["corrections"]) == (4, 1)


def test_a_corrected_protocol_is_not_written_again_unless_told(project, held):
    sid = project[1]
    d = held("Byggmöte 3", SAID)
    write(d, sid, [ATA], no=3)
    correct.check(d, "3.4.1", 1)
    assert (overview.detail(d)["corrections"], overview.detail(d)["later"]) == (1, None)
    with pytest.raises(ArgError, match="1 corrections"):
        write(d, sid, [ATA])
    assert "confirmed" in protocol.load(d)["points"][0]["checks"][0]
    protocol.answer(d, sid, json.dumps({"points": [ATA]}), discard=True)
    assert "confirmed" not in protocol.load(d)["points"][0]["checks"][0]


def test_who_was_there_follows_the_names_and_a_person_adds_who_said_nothing(project, held, capsys):
    sid = project[1]
    d = held("Byggmöte 3", [(0, "Maria Lindqvist", "Välkomna till byggmöte tre."), (9, "Talare 2", "Tack, då börjar vi med tidplanen.")])
    write(d, sid, no=3)
    assert protocol.load(d)["attendees"] == [{"name": "Maria Lindqvist", "role": "Projektledare"}, {"name": "Talare 2"}]
    there = correct.attend(d, "@anders-holm")
    assert there[2] | {"added": ""} == {"name": "Anders Holm", "role": "Beställarens ombud", "person": "anders-holm", "added": ""}
    assert correct.attend(d, "anders-holm") == there  # once is enough

    assert cli.main(["name", str(d), "S2", "@jonas-bergstrom"]) == 0  # as the app names a speaker
    capsys.readouterr()
    assert [(a["name"], a.get("role")) for a in protocol.load(d)["attendees"]] == [
        ("Maria Lindqvist", "Projektledare"), ("Jonas Bergström", "Platschef"), ("Anders Holm", "Beställarens ombud")]
    assert "- Jonas Bergström, Platschef\n- Anders Holm, Beställarens ombud\n" in (d / protocol.TEXT).read_text(encoding="utf-8")
    assert protocol.corrections(protocol.load(d)) == 1

    for who, gone in (("@jonas-bergstrom", True), ("@ingen", False)):  # he spoke; and nobody the project has
        with pytest.raises(ArgError):
            correct.attend(d, who, gone)
    assert [a["name"] for a in correct.attend(d, "@anders-holm", gone=True)] == ["Maria Lindqvist", "Jonas Bergström"]
    assert correct.attendees(held("Byggmöte 4", SAID)) is None  # no protocol, nothing to set


def test_the_command_takes_the_fields_on_stdin(project, held, capsys, monkeypatch):
    import io
    d = held("Byggmöte 3", SAID)
    write(d, project[1], [ATA], no=3)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"text": "ÄTA 14 beställs."}'))
    assert cli.main(["correct", "change", str(d), "3.4.1"]) == 0
    assert json.loads(capsys.readouterr().out)["text"] == "ÄTA 14 beställs."
    assert cli.main(["correct", "remove", str(d), "3.4.9"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "no point 3.4.9"}
    monkeypatch.setattr("sys.stdin", io.StringIO('{"points": [], "carried": []}'))
    assert cli.main(["protocol", str(d), "--series", project[1], "--answer"]) == 2
    assert "--discard" in json.loads(capsys.readouterr().out)["error"]
