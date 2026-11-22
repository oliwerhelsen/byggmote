import json

import pytest

from byggmote import ArgError, areas, overview, people, protocol, series, stommen

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


def project() -> dict:
    return next(a for a in areas.load()["areas"] if a.get("stommen") == PROJECT["id"])


def test_a_projekt_comes_with_its_roller_and_the_kontakter_who_hold_them(config):
    areas.load()
    assert stommen.take(given()) == {"project": "kv-eken-kontorshus", "name": "Kv. Eken kontorshus", "people": 3, "roles": 5,
                                     "vacant": 1, "left": []}
    a = project()
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
    a = project()
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
    assert protocol.held(project())["maria-l"] == "Projektledare, BAS-P"

    other = {"id": "2b0c3f11-8e5d-4f7a-a2c4-91d6e0b7c3f2", "name": "Kv. Linden"}  # the same person is a Kontakt of another Projekt
    stommen.take({"project": other, "roles": [{"id": "r2", "name": "Projektledare", "holderId": "k9", "substituteId": None}],
                  "contacts": [{"id": "k9", "name": "Maria Lindqvist", "email": "maria@norrstaden.example"}]})
    assert len(people.load()) == 3
    assert next(p for p in people.load() if p["id"] == "maria-l")["stommen"] == {PROJECT["id"]: "k-maria", other["id"]: "k9"}


def test_a_vacant_roll_can_be_given_a_point(config, held):
    areas.load()
    stommen.take(given())
    aid = project()["id"]
    sid = series.start(aid, {"name": "Byggmöte"})["id"]
    d = areas.transcripts(project()) / "Byggmöte 1"
    d.mkdir(parents=True)
    from byggmote import meeting
    ids = {p["name"]: p["id"] for p in people.load()}
    who = list(dict.fromkeys(s for _, s, _ in SAID))
    meeting.save(d, {"schema": meeting.SCHEMA, "title": "Byggmöte 1", "area": aid, "lang": "sv", "status": "review",
                     "recorded_at": "2026-11-19T09:00:00+01:00", "duration": 3120,
                     "speakers": [{"id": f"S{i}", "name": n, "person": ids.get(n), "track": "1", "cluster": None, "embedding": None}
                                  for i, n in enumerate(who, 1)],
                     "segments": [{"id": i, "start": float(t), "end": float(t) + 4, "speaker": f"S{who.index(s) + 1}", "text": text, "words": []}
                                  for i, (t, s, text) in enumerate(SAID, 1)]})
    assert protocol.request(d, sid)["schema"]["properties"]["points"]["items"]["properties"]["role"]["anyOf"][0]["enum"][-1] == "Konstruktör"
    protocol.answer(d, sid, json.dumps({"points": [point(kind="question", text="Måtten skickas.", role="konstruktör")]}))
    p = protocol.load(d)
    assert (p["points"][0]["role"], p["points"][0]["checks"]) == ("Konstruktör", [])
    assert p["attendees"][0] == {"name": "Maria Lindqvist", "role": "Projektledare, BAS-P"}


@pytest.mark.parametrize("bad", [
    "text", {}, {"project": {"id": "x"}, "roles": [], "contacts": []}, {"project": PROJECT, "roles": [], "contacts": "inga"},
    {"project": PROJECT, "roles": [{"id": "r", "name": "Platschef", "holderId": "k-ingen"}], "contacts": []},
    {"project": PROJECT, "roles": [{"id": "r"}], "contacts": []}, {"project": PROJECT, "roles": [], "contacts": [{"name": "Utan id"}]}])
def test_an_answer_that_is_not_stommens_is_refused_and_nothing_is_made(config, bad):
    areas.load()
    with pytest.raises(ArgError):
        stommen.take(bad)
    assert not any(a.get("stommen") for a in areas.load()["areas"])
