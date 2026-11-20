import pytest

from byggmote import areas, knowledge, meeting, people, series

PEOPLE = (("Maria Lindqvist", "Projektledare"), ("Anders Holm", "Beställarens ombud"), ("Jonas Bergström", "Platschef"))


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    """A knowledge base of its own per test: nothing reads or writes the real folders."""
    monkeypatch.setenv("BYGGMOTE_CONFIG", str(tmp_path / "config"))
    monkeypatch.setattr(knowledge, "_written", None)
    return tmp_path


@pytest.fixture
def project():
    """A project with three roles held and a byggmöte series: (project id, series id)."""
    areas.load()  # makes the knowledge base, as the CLI does before any command
    a = areas.add({"name": "Kv. Eken kontorshus"})
    for name, role in PEOPLE:
        people.add({"name": name, "areas": [{"area": a["id"], "role": role}]})
    return a["id"], series.start(a["id"], {"name": "Byggmöte"})["id"]


@pytest.fixture
def held(project):
    """`held(name, said)`: a transcribed meeting in the project from lines of (seconds, speaker, text); its folder."""
    aid, _ = project

    def make(name: str, said: list[tuple]):
        ids = {p["name"]: p["id"] for p in people.load()}
        who = list(dict.fromkeys(s for _, s, _ in said))
        m = {"schema": meeting.SCHEMA, "title": name, "area": aid, "lang": "sv", "status": "review",
             "recorded_at": "2026-11-19T09:00:00+01:00", "duration": 3120,
             "speakers": [{"id": f"S{i}", "name": n, "person": ids.get(n), "track": "1", "cluster": None, "embedding": None}
                          for i, n in enumerate(who, 1)],
             "segments": [{"id": i, "start": float(t), "end": float(t) + 4, "speaker": f"S{who.index(s) + 1}", "text": text, "words": []}
                          for i, (t, s, text) in enumerate(said, 1)]}
        d = areas.transcripts(areas.get(areas.load(), aid)) / name
        d.mkdir(parents=True)
        meeting.save(d, m)
        return d
    return make
