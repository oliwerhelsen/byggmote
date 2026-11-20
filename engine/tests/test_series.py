import pytest

from byggmote import ArgError, areas, knowledge, series


def test_a_new_series_gets_the_byggmote_headings_numbered_from_one(project):
    aid, sid = project
    s = series.get(series.load(areas.get(areas.load(), aid)), sid)
    assert [h["no"] for h in s["headings"]] == list(range(1, 12))
    assert s["headings"][3]["name"] == "Ekonomi"
    assert s["headings"][0]["fill"] == "attendees"


def test_the_first_series_teaches_the_project_construction_terms(project):
    aid, _ = project
    assert "ÄTA = äta" in areas.get(areas.load(), aid)["vocabulary"]


def test_a_second_series_with_the_same_name_gets_its_own_id(project):
    aid, sid = project
    assert series.start(aid, {"name": "Byggmöte"})["id"] == f"{sid}-2"


def test_a_heading_is_renamed_under_its_number(project):
    aid, sid = project
    h = series.heading(aid, sid, {"no": 4, "name": "Ekonomi och ÄTA"})
    assert h == {"no": 4, "name": "Ekonomi och ÄTA", "hint": "ÄTA, betalningsplan, mängdreglering"}
    assert series.heading(aid, sid, {"no": 1, "name": "Deltagare"})["fill"] == "attendees"


def test_a_new_heading_goes_last(project):
    aid, sid = project
    assert series.heading(aid, sid, {"name": "Samordning installationer", "hint": "El, rör, vent"})["no"] == 12


def test_a_heading_that_is_not_there_cannot_be_renamed(project):
    aid, sid = project
    with pytest.raises(ArgError):
        series.heading(aid, sid, {"no": 40, "name": "Ekonomi"})


def test_a_meeting_takes_the_next_number_and_keeps_it(project, held):
    aid, sid = project
    area = areas.get(areas.load(), aid)
    first, second = held("Byggmöte 1", [(0, "Maria Lindqvist", "Välkomna.")]), held("Byggmöte 2", [(0, "Maria Lindqvist", "Välkomna.")])
    with knowledge.locked(knowledge.folder()):
        assert series.file(area, sid, first) == 1
        assert series.file(area, sid, second) == 2
        assert series.file(area, sid, first) == 1
        with pytest.raises(ArgError):
            series.file(area, sid, second, 1)
