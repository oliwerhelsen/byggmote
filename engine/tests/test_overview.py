import json

from byggmote import overview, protocol

from test_protocol import SAID, point


def test_projects_come_with_their_roles_and_series(project):
    aid, sid = project
    (only,) = overview.projects()["projects"]
    assert (only["id"], only["name"]) == (aid, "Kv. Eken kontorshus")
    assert only["people"][0] == {"id": "maria-lindqvist", "name": "Maria Lindqvist", "role": "Projektledare"}
    assert only["series"] == [{"id": sid, "name": "Byggmöte", "next": 1}]


def test_a_projects_meetings_say_where_they_stand(project, held):
    aid, sid = project
    first, second = held("Byggmöte 3", SAID), held("Byggmöte 4", [(0, "Talare 1", "Välkomna.")])
    protocol.answer(first, sid, json.dumps({"points": [point(kind="todo"), point(kind="decision", text="ÄTA 14 godkänns till 86 500 kr.")]}), 3)
    rows = {r["title"]: r for r in overview.meetings(aid)}
    assert (rows["Byggmöte 3"]["series"], rows["Byggmöte 3"]["no"]) == (sid, 3)
    assert rows["Byggmöte 3"]["protocol"] == {"status": "draft", "points": 2, "carried": 0, "open": 1, "checks": 1}
    assert (rows["Byggmöte 4"]["no"], rows["Byggmöte 4"]["protocol"], rows["Byggmöte 4"]["unnamed"]) == (None, None, 1)


def test_one_meeting_has_its_lines_and_its_protocol(project, held):
    sid = project[1]
    d = held("Byggmöte 3", SAID)
    protocol.answer(d, sid, json.dumps({"points": [point(kind="decision")]}), 3)
    got = overview.detail(d)
    assert got["lines"][3] == {"id": 4, "at": 1062.0, "speaker": "S3", "who": "Anders Holm",
                               "text": "Beställaren godkänner ÄTA 14 till fast pris åttiosex och fem."}
    assert got["speakers"][0] == {"id": "S1", "name": "Maria Lindqvist", "person": "maria-lindqvist"}
    assert (got["no"], got["audio"], got["protocol"]["points"][0]["no"]) == (3, False, "3.4.1")
