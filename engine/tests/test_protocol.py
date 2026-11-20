import json

import pytest

from byggmote import ArgError, protocol, series

SAID = [
    (0, "Maria Lindqvist", "Välkomna till byggmöte tre för kvarteret Eken."),
    (494, "Jonas Bergström", "Stomresningen på plan tre är klar och vi följer tidplanen."),
    (860, "Maria Lindqvist", "Då går vi till ekonomin och mängdregleringen av schakten."),
    (1062, "Anders Holm", "Beställaren godkänner ÄTA 14 till fast pris åttiosex och fem."),
    (1265, "Jonas Bergström", "Jag skickar underlaget för mängdregleringen av schakt senast fredag."),
]


def point(**given) -> dict:
    return {"heading": 4, "kind": "note", "text": "En upplysning.", "time": "17:42",
            "quote": "Beställaren godkänner ÄTA 14 till fast pris"} | given


def write(d, sid, points=(), carried=(), no=None) -> dict:
    protocol.answer(d, sid, json.dumps({"points": list(points), "carried": list(carried)}), no)
    return protocol.load(d)


def test_points_are_numbered_per_heading_in_the_order_they_are_said(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [
        point(text="Underlag för mängdreglering skickas.", kind="todo", time="21:05", quote="Jag skickar underlaget för mängdregleringen"),
        point(text="ÄTA 14 godkänns.", kind="decision"),
        point(heading=3, text="Stommen på plan tre är klar.", time="08:14", quote="Stomresningen på plan tre är klar")], no=3)
    assert [(x["no"], x["text"]) for x in p["points"]] == [
        ("3.3.1", "Stommen på plan tre är klar."), ("3.4.1", "ÄTA 14 godkänns."), ("3.4.2", "Underlag för mängdreglering skickas.")]


def test_a_point_the_transcript_does_not_have_is_not_shown(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(text="Vite utgår med 50 000 kr per vecka.", quote="vite utgår med femtiotusen kronor per vecka")])
    assert p["points"] == []
    assert p["dropped"] == [{"reason": "no-source", "text": "Vite utgår med 50 000 kr per vecka.", "time": "17:42",
                             "quote": "vite utgår med femtiotusen kronor per vecka"}]


def test_a_quote_of_two_words_is_no_source(project, held):
    d = held("Byggmöte 3", SAID)
    assert write(d, project[1], [point(quote="Beställaren godkänner")])["points"] == []


def test_the_same_words_in_another_order_are_no_source(project, held):
    d = held("Byggmöte 3", SAID)
    assert write(d, project[1], [point(quote="fast pris godkänner beställaren till ÄTA 14")])["points"] == []


def test_a_quote_is_found_however_its_numbers_are_written(project, held):
    d = held("Byggmöte 3", [(1062, "Anders Holm", "Beställaren godkänner ÄTA 14 till fast pris 86.500 kr.")])
    p = write(d, project[1], [point(quote="godkänner ÄTA 14 till fast pris 86 500 kr")])
    assert p["points"][0]["at"] == 1062.0


def test_a_point_points_at_the_line_that_has_its_quote_whatever_time_the_model_gave(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(time="02:00")])
    assert (p["points"][0]["at"], p["points"][0]["line"]) == (1062.0, 4)


def test_an_amount_is_always_checked_against_what_the_recording_has(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(kind="decision", text="Beställaren godkänner ÄTA 14 till fast pris 86 500 kr.")])
    assert p["points"][0]["checks"] == [
        {"code": "amount", "value": "86 500 kr", "said": "Beställaren godkänner ÄTA 14 till fast pris åttiosex och fem."}]


def test_a_role_is_the_projects_own_or_a_check(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(kind="todo", text="Underlag skickas.", role="platschef"),
                              point(heading=5, kind="question", text="Frågan skickas.", role="Konstruktören")])
    assert (p["points"][0]["role"], p["points"][0]["checks"]) == ("Platschef", [])
    assert (p["points"][1]["role"], p["points"][1]["checks"]) == (None, [{"code": "role", "said": "Konstruktören"}])


def test_a_decision_is_never_left_open_and_a_new_risk_never_closed(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(kind="decision", open=True), point(heading=5, kind="question"), point(heading=8, kind="risk", open=False)])
    assert [x["open"] for x in p["points"]] == [False, True, True]


def test_only_what_stays_open_has_a_role_and_a_day(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(kind="note", role="Platschef", due="2026-12-03"), point(heading=5, kind="todo", role="Platschef", due="2026-12-03")])
    assert [(x["role"], x["due"]) for x in p["points"]] == [(None, None), ("Platschef", "2026-12-03")]


def test_the_model_writes_no_points_under_the_attendees(project, held):
    d = held("Byggmöte 3", SAID)
    p = write(d, project[1], [point(heading=1), point(heading=99)])
    assert p["points"] == []
    assert [x["reason"] for x in p["dropped"]] == ["heading", "heading"]
    assert p["attendees"][0] == {"name": "Maria Lindqvist", "role": "Projektledare"}


def test_an_open_point_follows_along_until_a_meeting_closes_it(project, held):
    aid, sid = project
    todo = point(kind="todo", text="Underlag för mängdreglering av schakt.", role="Platschef", due="2026-11-12",
                 time="21:05", quote="Jag skickar underlaget för mängdregleringen")
    write(held("Byggmöte 3", SAID), sid, [point(kind="decision", text="ÄTA 14 godkänns."), todo], no=3)
    assert [p["no"] for h in series.agenda(aid, sid)["headings"] for p in h["open"]] == ["3.4.2"]

    p4 = write(held("Byggmöte 4", SAID[:2]), sid)  # the point is not taken up
    assert [(x["no"], x["open"], x["raised"], x["at"]) for x in p4["points"]] == [("3.4.2", True, False, None)]
    assert series.agenda(aid, sid)["headings"][3]["open"][0]["due"] == "2026-11-12"

    p5 = write(held("Byggmöte 5", SAID), sid, carried=[
        {"no": "3.4.2", "text": "Underlaget är skickat.", "open": False, "time": "21:05", "quote": "Jag skickar underlaget för mängdregleringen"}])
    assert [(x["no"], x["since"], x["open"], x["follow"], x["at"]) for x in p5["points"]] == [("3.4.2", 3, False, "Underlaget är skickat.", 1265.0)]
    assert series.agenda(aid, sid)["no"] == 6
    assert not any(h["open"] for h in series.agenda(aid, sid)["headings"])


def test_a_follow_up_the_transcript_does_not_have_leaves_the_point_open(project, held):
    sid = project[1]
    write(held("Byggmöte 3", SAID), sid, [point(kind="todo", text="Underlag skickas.")], no=3)
    p = write(held("Byggmöte 4", SAID), sid, carried=[
        {"no": "3.4.1", "text": "Klart.", "open": False, "time": "21:05", "quote": "underlaget är redan skickat till beställaren"},
        {"no": "9.9.9", "text": "Okänd punkt.", "time": "21:05", "quote": "Jag skickar underlaget för mängdregleringen"}])
    assert [(x["no"], x["open"], x["raised"]) for x in p["points"]] == [("3.4.1", True, False)]
    assert [x["reason"] for x in p["dropped"]] == ["no-source", "unknown-point"]


@pytest.mark.parametrize("source", [{"time": None, "quote": None}, {"time": "00:00", "quote": "Underlag skickas till beställaren."}])
def test_an_open_point_only_listed_again_was_not_taken_up(project, held, source):
    sid = project[1]
    write(held("Byggmöte 3", SAID), sid, [point(kind="todo", text="Underlag skickas.")], no=3)
    p = write(held("Byggmöte 4", SAID), sid, carried=[{"no": "3.4.1", "text": "Underlag skickas.", "open": True} | source])
    assert [(x["no"], x["raised"]) for x in p["points"]] == [("3.4.1", False)]
    assert p["dropped"] == []


def test_a_follow_up_that_only_repeats_the_point_shows_the_line_instead(project, held):
    sid = project[1]
    write(held("Byggmöte 3", SAID), sid, [point(kind="todo", text="Underlag skickas.")], no=3)
    d = held("Byggmöte 4", SAID)
    p = write(d, sid, carried=[{"no": "3.4.1", "text": "Underlag skickas.", "time": "21:05", "quote": "Jag skickar underlaget för mängdregleringen"}])
    assert (p["points"][0]["raised"], p["points"][0]["follow"]) == (True, None)
    assert "  - På mötet sägs: ”Jag skickar underlaget för mängdregleringen av schakt senast fredag.” [21:05]\n" in (d / protocol.TEXT).read_text(encoding="utf-8")


def test_a_protocol_a_later_meeting_builds_on_is_not_written_again(project, held):
    sid = project[1]
    first = held("Byggmöte 3", SAID)
    write(first, sid, [point(kind="todo")], no=3)
    write(held("Byggmöte 4", SAID), sid)
    with pytest.raises(ArgError):
        write(first, sid, [point()])


def test_the_protocol_reads_as_a_document(project, held):
    sid = project[1]
    write(held("Byggmöte 3", SAID), sid, [point(kind="todo", text="Underlag skickas", role="Platschef", due="2026-11-12")], no=3)
    d = held("Byggmöte 4", SAID)
    write(d, sid, [point(kind="decision", text="ÄTA 14 godkänns till fast pris 86 500 kr.")])
    text = (d / protocol.TEXT).read_text(encoding="utf-8")
    assert text.startswith("# Protokoll, byggmöte 4\n\nKv. Eken kontorshus. 2026-11-19, 52 minuter. Utkast, inte justerat.\n")
    assert "## 1. Närvarande\n\n- Maria Lindqvist, Projektledare\n" in text
    assert "## 7. Kvalitet och miljö\n\nInget noterat.\n" in text
    assert "- **3.4.1** Att göra, kvarstår från byggmöte 3. Underlag skickas. Ansvarig: Platschef. Senast 2026-11-12.\n  - Togs inte upp på mötet.\n" in text
    assert "- **4.4.1** Beslut. ÄTA 14 godkänns till fast pris 86 500 kr. [17:42]\n  - Kontrollera beloppet 86 500 kr. I inspelningen sägs: ”Beställaren godkänner" in text


def test_the_prompt_has_the_agenda_the_open_points_and_the_transcript(project, held, config):
    sid = project[1]
    write(held("Byggmöte 3", SAID), sid, [point(kind="todo", text="Underlag skickas.", role="Platschef")], no=3)
    d = held("Byggmöte 4", SAID)
    (d / protocol.MARKS).write_text(json.dumps({"headings": [{"no": 4, "at": 860}], "marks": [{"kind": "decision", "at": 1062}]}), encoding="utf-8")
    r = protocol.request(d, sid)
    assert r["no"] == 4
    assert "protokollet för byggmöte 4 i projektet Kv. Eken kontorshus. Mötet hölls torsdag 2026-11-19." in r["prompt"]
    assert "4. Ekonomi: ÄTA, betalningsplan, mängdreglering" in r["prompt"]
    assert "Roller i projektet: Projektledare, Beställarens ombud, Platschef" in r["prompt"]
    assert "- 3.4.1 (rubrik 4, Att göra, ansvarig Platschef): Underlag skickas." in r["prompt"]
    assert "(Här trycktes rubrik 4. Ekonomi)\n[14:20] Maria Lindqvist: Då går vi till ekonomin" in r["prompt"]
    assert "(Här sattes märket Beslut)\n[17:42] Anders Holm: Beställaren godkänner" in r["prompt"]


def test_a_model_held_to_the_schema_can_only_name_what_there_is(project, held):
    sid = project[1]
    d = held("Byggmöte 3", SAID)
    first = protocol.request(d, sid, 3)["schema"]
    assert first["properties"]["carried"] == {"type": "array", "maxItems": 0}
    fields = first["properties"]["points"]["items"]["properties"]
    assert fields["heading"]["enum"] == list(range(2, 12))  # not 1, the attendees
    assert fields["kind"]["enum"] == list(protocol.KINDS)
    assert fields["role"]["anyOf"][0]["enum"] == ["Projektledare", "Beställarens ombud", "Platschef"]
    write(d, sid, [point(kind="todo", text="Underlag skickas.")], no=3)
    later = protocol.request(held("Byggmöte 4", SAID), sid)["schema"]
    assert later["properties"]["carried"]["items"]["properties"]["no"]["enum"] == ["3.4.1"]


def test_an_answer_is_read_with_or_without_text_around_it():
    assert protocol.read('Här är protokollet:\n```json\n{"points": [], "carried": []}\n```\n') == {"points": [], "carried": []}
    for bad in ("Jag kan inte läsa utskriften.", '{"points": "inga"}', '{"points": [}'):
        with pytest.raises(ValueError):
            protocol.read(bad)
