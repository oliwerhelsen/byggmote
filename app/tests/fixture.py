"""A small project for the app's tests, in the knowledge base BYGGMOTE_CONFIG names: three people with roles, a byggmöte
series and two held meetings with protocols. The engine itself writes it, from answers a model could have given, so the
app is tested against the real files and no model runs."""
import json

from byggmote import areas, meeting, people, protocol, series

SAID = [
    (0, "Maria Lindqvist", "Välkomna till byggmötet för kvarteret Eken."),
    (494, "Jonas Bergström", "Stomresningen på plan tre är klar och vi följer tidplanen."),
    (860, "Maria Lindqvist", "Då går vi till ekonomin och mängdregleringen av schakten."),
    (1062, "Anders Holm", "Beställaren godkänner ÄTA 14 till fast pris åttiosex och fem."),
    (1265, "Jonas Bergström", "Jag skickar underlaget för mängdregleringen av schakt senast fredag."),
]

areas.load()
project = areas.add({"name": "Kv. Eken kontorshus"})
for name, role in (("Maria Lindqvist", "Projektledare"), ("Anders Holm", "Beställarens ombud"), ("Jonas Bergström", "Platschef")):
    people.add({"name": name, "areas": [{"area": project["id"], "role": role}]})
sid = series.start(project["id"], {"name": "Byggmöte"})["id"]
ids = {p["name"]: p["id"] for p in people.load()}


def held(name: str, day: str, said: list[tuple]):
    who = list(dict.fromkeys(s for _, s, _ in said))
    m = {"schema": meeting.SCHEMA, "title": name, "area": project["id"], "lang": "sv", "status": "review",
         "recorded_at": f"{day}T09:00:00+01:00", "duration": 3120,
         "speakers": [{"id": f"S{i}", "name": n, "person": ids.get(n), "track": "1", "cluster": None, "embedding": None}
                      for i, n in enumerate(who, 1)],
         "segments": [{"id": i, "start": float(t), "end": float(t) + 4, "speaker": f"S{who.index(s) + 1}", "text": text, "words": []}
                      for i, (t, s, text) in enumerate(said, 1)]}
    d = areas.transcripts(areas.get(areas.load(), project["id"])) / name
    d.mkdir(parents=True)
    meeting.save(d, m)
    return d


protocol.answer(held("Byggmöte 3", "2026-10-22", SAID), sid, json.dumps({"carried": [], "points": [
    {"heading": 4, "kind": "todo", "text": "Platschefen lämnar underlag för mängdreglering av schakt.", "role": "Platschef",
     "due": "2026-11-12", "open": True, "time": "21:05", "quote": "Jag skickar underlaget för mängdregleringen"}]}), 3)
protocol.answer(held("Byggmöte 4", "2026-11-05", SAID[:4]), sid, json.dumps({"carried": [], "points": [
    {"heading": 3, "kind": "note", "text": "Stommen på plan tre är klar.", "time": "08:14", "quote": "Stomresningen på plan tre är klar"},
    {"heading": 4, "kind": "decision", "text": "Beställaren godkänner ÄTA 14 till fast pris 86 500 kr.", "time": "17:42",
     "quote": "Beställaren godkänner ÄTA 14 till fast pris"}]}))
