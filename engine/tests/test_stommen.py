import json

import pytest

from byggmote import ArgError, areas, correct, meeting, overview, people, protocol, series, stommen

from test_protocol import SAID, point

PROJECT = {"id": "7d1f0a52-4c1e-4a0b-9b1e-2f6c8d3e5a10", "name": "Kv. Eken kontorshus"}
MARIA = {"id": "k-maria", "name": "Maria Lindqvist", "organization": "Norrstaden Fastigheter AB", "email": "maria@norrstaden.example"}
ANDERS = {"id": "k-anders", "name": "Anders Holm", "organization": "Norrstaden Fastigheter AB", "email": None}
JONAS = {"id": "k-jonas", "name": "Jonas Bergström", "organization": "Bergström Bygg AB", "email": "jonas@bergstrom.example"}
ROLES = [{"id": "r-pl", "name": "Projektledare", "description": None, "holderId": "k-maria", "substituteId": "k-anders"},
         {"id": "r-basp", "name": "BAS-P", "holderId": "k-maria", "substituteId": None},
         {"id": "r-ombud", "name": "Beställarens ombud", "holderId": "k-anders", "substituteId": None},
         {"id": "r-plats", "name": "Platschef", "holderId": "k-jonas", "substituteId": None},
         {"id": "r-k", "name": "Konstruktör", "holderId": None, "substituteId": None}]


def given(**changed) -> dict:
    return {"project": PROJECT, "roles": ROLES, "contacts": [MARIA, ANDERS, JONAS]} | changed


def eken() -> dict:
    return next(a for a in areas.load()["areas"] if a.get("stommen") == PROJECT["id"])


def test_a_projekt_comes_with_its_roller_and_the_kontakter_who_hold_them(config):
    areas.load()
    assert stommen.take(given()) == {"project": "kv-eken-kontorshus", "name": "Kv. Eken kontorshus", "people": 3, "roles": 5,
                                     "vacant": 1, "left": []}
    a = eken()
    assert protocol.roles(a) == ["Projektledare", "BAS-P", "Beställarens ombud", "Platschef", "Konstruktör"]  # the vacant one too
    assert protocol.held(a) == {"maria-lindqvist": "Projektledare, BAS-P", "anders-holm": "Beställarens ombud", "jonas-bergstrom": "Platschef"}
    assert a["roles"][0] == {"id": "r-pl", "name": "Projektledare", "holder": "maria-lindqvist", "substitute": "anders-holm"}
    maria = next(p for p in people.load() if p["id"] == "maria-lindqvist")
    assert (maria["email"], maria["stommen"]) == ("maria@norrstaden.example", {PROJECT["id"]: "k-maria"})

    (shown,) = overview.projects()["projects"]
    assert (shown["stommen"], shown["roles"][-1]) == (PROJECT["id"], "Konstruktör")
    assert shown["people"][0] == {"id": "maria-lindqvist", "name": "Maria Lindqvist", "role": "Projektledare, BAS-P"}


def test_stommen_wins_when_it_is_asked_again(config):
    areas.load()
    stommen.take(given())
    again = stommen.take(given(
        project=PROJECT | {"name": "Kv. Eken, kontorshus"},
        contacts=[MARIA | {"name": "Maria Lindqvist Berg"}, ANDERS],
        roles=[r | ({"holderId": None} if r["id"] == "r-plats" else {}) for r in ROLES]))
    assert (again["project"], again["name"], again["people"], again["vacant"], again["left"]) == (
        "kv-eken-kontorshus", "Kv. Eken, kontorshus", 2, 2, ["jonas-bergstrom"])
    a = eken()
    assert [m["person"] for m in a["people"]] == ["maria-lindqvist", "anders-holm"]
    ps = {p["id"]: p for p in people.load()}
    assert ps["maria-lindqvist"]["name"] == "Maria Lindqvist Berg"  # the same person under the name Stommen has now
    assert "stommen" not in ps["jonas-bergstrom"]  # out of the project, still a person: his meetings name him
    assert len(areas.load()["areas"]) == len({a["id"] for a in areas.load()["areas"]})
    assert sum(a.get("stommen") == PROJECT["id"] for a in areas.load()["areas"]) == 1


def test_a_kontakt_is_a_person_byggmote_already_knows(config):
    areas.load()
    people.add({"name": "Maria L", "email": "Maria@Norrstaden.example"})  # known by another name, the same e-mail
    people.add({"name": "anders holm"})  # the same name, no e-mail
    stommen.take(given())
    ps = people.load()
    assert sorted(p["id"] for p in ps) == ["anders-holm", "jonas-bergstrom", "maria-l"]
    assert next(p for p in ps if p["id"] == "maria-l")["name"] == "Maria Lindqvist"
    assert protocol.held(eken())["maria-l"] == "Projektledare, BAS-P"

    other = {"id": "2b0c3f11-8e5d-4f7a-a2c4-91d6e0b7c3f2", "name": "Kv. Linden"}  # the same person is a Kontakt of another Projekt
    stommen.take({"project": other, "roles": [{"id": "r2", "name": "Projektledare", "holderId": "k9", "substituteId": None}],
                  "contacts": [{"id": "k9", "name": "Maria Lindqvist", "email": "maria@norrstaden.example"}]})
    assert len(people.load()) == 3
    assert next(p for p in people.load() if p["id"] == "maria-l")["stommen"] == {PROJECT["id"]: "k-maria", other["id"]: "k9"}


def hold(name: str, said: list[tuple], day: str = "2026-11-19"):
    """A transcribed meeting in Stommen's project, as conftest's `held` makes one in a local project: its folder."""
    a = eken()
    ids = {p["name"]: p["id"] for p in people.load()}
    who = list(dict.fromkeys(s for _, s, _ in said))
    d = areas.transcripts(a) / name
    d.mkdir(parents=True)
    meeting.save(d, {"schema": meeting.SCHEMA, "title": name, "area": a["id"], "lang": "sv", "status": "review",
                     "recorded_at": f"{day}T09:00:00+01:00", "duration": 3120,
                     "speakers": [{"id": f"S{i}", "name": n, "person": ids.get(n), "track": "1", "cluster": None, "embedding": None}
                                  for i, n in enumerate(who, 1)],
                     "segments": [{"id": i, "start": float(t), "end": float(t) + 4, "speaker": f"S{who.index(s) + 1}", "text": text, "words": []}
                                  for i, (t, s, text) in enumerate(said, 1)]})
    return d


def test_a_vacant_roll_can_be_given_a_point(config):
    areas.load()
    stommen.take(given())
    sid = series.start(eken()["id"], {"name": "Byggmöte"})["id"]
    d = hold("Byggmöte 1", SAID)
    assert protocol.request(d, sid)["schema"]["properties"]["points"]["items"]["properties"]["role"]["anyOf"][0]["enum"][-1] == "Konstruktör"
    protocol.answer(d, sid, json.dumps({"points": [point(kind="question", text="Måtten skickas.", role="konstruktör")]}))
    p = protocol.load(d)
    assert (p["points"][0]["role"], p["points"][0]["checks"]) == ("Konstruktör", [])
    assert p["attendees"][0] == {"name": "Maria Lindqvist", "role": "Projektledare, BAS-P"}


def test_a_protocol_goes_to_stommen_with_where_each_point_was_said(config):
    areas.load()
    stommen.take(given())
    sid = series.start(eken()["id"], {"name": "Byggmöte"})["id"]
    todo = point(kind="todo", text="Underlag för mängdreglering skickas.", role="Platschef", due="2026-11-26",
                 time="21:05", quote="Jag skickar underlaget för mängdregleringen")
    protocol.answer(hold("Byggmöte 3", SAID, "2026-10-22"), sid, json.dumps({"points": [todo]}), 3)
    d = hold("Byggmöte 4", SAID + [(1500, "Talare 4", "Vi har en fråga om måtten på ritningen.")], "2026-11-05")
    protocol.answer(d, sid, json.dumps({
        "points": [point(kind="decision", text="Beställaren godkänner ÄTA 14 till fast pris 86 500 kr."),
                   point(heading=5, kind="question", text="Måtten på ritningen saknas.", role="Konstruktör", time="25:00",
                         quote="Vi har en fråga om måtten på ritningen")],
        "carried": [{"no": "3.4.1", "text": "Underlaget kommer på fredag.", "open": True, "time": "21:05",
                     "quote": "Jag skickar underlaget för mängdregleringen"}]}))

    with pytest.raises(ArgError, match="1 checks are left"):  # the amount is not read against the recording yet
        stommen.minutes(d)
    correct.check(d, "4.4.1", 1)
    correct.change(d, "4.5.1", {"text": "Måtten för ursparingen saknas på ritning K-20."})
    correct.add(d, {"heading": 3, "kind": "note", "text": "Tidplanen hålls."})
    correct.remove(d, "4.3.1")
    correct.add(d, {"heading": 3, "kind": "note", "text": "Stommen på plan tre är klar.", "line": 2})

    sent = stommen.minutes(d)
    assert sent["project"] == PROJECT["id"]
    m = sent["minutes"]
    assert (m["series"], m["meeting"]) == ({"key": sid, "name": "Byggmöte"}, {"number": 4, "heldOn": "2026-11-05", "durationSeconds": 3120})
    assert m["headings"][3] == {"number": 4, "name": "Ekonomi"}
    assert m["attendees"][:2] == [{"name": "Maria Lindqvist", "role": "Projektledare, BAS-P", "contactId": "k-maria"},
                                  {"name": "Jonas Bergström", "role": "Platschef", "contactId": "k-jonas"}]
    assert m["attendees"][-1] == {"name": "Talare 4", "role": None, "contactId": None}
    assert m["text"].startswith("# Protokoll, byggmöte 4\n")

    items = {x["number"]: x for x in m["items"]}
    assert sorted(items) == ["3.4.1", "4.3.2", "4.4.1", "4.5.1"]  # the point a person took out is not sent
    assert items["4.4.1"] == {
        "number": "4.4.1", "heading": 4, "kind": "decision", "text": "Beställaren godkänner ÄTA 14 till fast pris 86 500 kr.",
        "roleId": None, "due": None, "open": False, "since": 4, "followUp": None, "saidAt": 1062,
        "quote": "Beställaren godkänner ÄTA 14 till fast pris åttiosex och fem.", "speaker": {"name": "Anders Holm", "contactId": "k-anders"},
        "written": "model", "confirmedAmounts": ["86 500 kr"]}
    carried = items["3.4.1"]
    assert (carried["since"], carried["open"], carried["followUp"], carried["roleId"], carried["due"], carried["saidAt"]) == (
        3, True, "Underlaget kommer på fredag.", "r-plats", "2026-11-26", 1265)
    assert (items["4.5.1"]["written"], items["4.5.1"]["roleId"], items["4.5.1"]["speaker"]) == (
        "changed", "r-k", {"name": "Talare 4", "contactId": None})  # a vacant Roll, and a speaker nobody has named
    assert (items["4.3.2"]["written"], items["4.3.2"]["saidAt"], items["4.3.2"]["speaker"]["name"]) == ("person", 494, "Jonas Bergström")


def test_a_protocol_is_not_sent_for_a_roll_stommen_no_longer_has(config):
    areas.load()
    stommen.take(given())
    sid = series.start(eken()["id"], {"name": "Byggmöte"})["id"]
    d = hold("Byggmöte 1", SAID)
    protocol.answer(d, sid, json.dumps({"points": [point(kind="todo", text="Underlag skickas.", role="Platschef")]}))
    assert stommen.minutes(d)["minutes"]["items"][0]["roleId"] == "r-plats"
    stommen.take(given(roles=[r | ({"name": "Arbetschef"} if r["id"] == "r-plats" else {}) for r in ROLES]))  # renamed in Stommen
    with pytest.raises(ArgError, match="Stommen has no Roll Platschef"):
        stommen.minutes(d)

    with pytest.raises(ArgError, match="no protocol"):
        stommen.minutes(hold("Byggmöte 2", SAID))


def test_a_project_of_our_own_has_nothing_to_send(project, held):
    d = held("Byggmöte 3", SAID)
    protocol.answer(d, project[1], json.dumps({"points": [point(kind="note")]}), 3)
    with pytest.raises(ArgError, match="not one of Stommen's"):
        stommen.minutes(d)


@pytest.mark.parametrize("bad", [
    "text", {}, {"project": {"id": "x"}, "roles": [], "contacts": []}, {"project": PROJECT, "roles": [], "contacts": "inga"},
    {"project": PROJECT, "roles": [{"id": "r", "name": "Platschef", "holderId": "k-ingen"}], "contacts": []},
    {"project": PROJECT, "roles": [{"id": "r"}], "contacts": []}, {"project": PROJECT, "roles": [], "contacts": [{"name": "Utan id"}]}])
def test_an_answer_that_is_not_stommens_is_refused_and_nothing_is_made(config, bad):
    areas.load()
    with pytest.raises(ArgError):
        stommen.take(bad)
    assert not any(a.get("stommen") for a in areas.load()["areas"])
