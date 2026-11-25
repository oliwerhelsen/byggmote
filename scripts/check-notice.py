#!/usr/bin/env python3
"""Fails when NOTICE.md is out of date: a model or a library the code uses and the document does not list, or lists
with another version, commit or licence. `python3 scripts/check-notice.py`, from anywhere.

Checked: every model repo in models.py with its commit and licence; every direct dependency of the engine (pyproject.toml,
versions from uv.lock) and of the app (package.json, versions and licences from package-lock.json). Not checked: the
licence of a Python library (the lock has none), and what the libraries pull in (the SBOM lists that)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import supply  # noqa: E402

bad: list[str] = []


def same(what: str, got: set[str], want: set[str]):
    for x in sorted(want - got):
        bad.append(f"{what}: {x} is in the code and not in NOTICE.md")
    for x in sorted(got - want):
        bad.append(f"{what}: {x} is in NOTICE.md and not in the code")


# The models
listed = {r[0]: (r[1], r[2]) for r in supply.table("Which copy of each model")}
code = supply.models()
same("models", set(listed), set(code))
for repo, (commit, licence) in code.items():
    if repo in listed and listed[repo] != (commit, licence):
        bad.append(f"models: {repo} is {commit} ({licence}) in models.py and {listed[repo][0]} ({listed[repo][1]}) in NOTICE.md")

# The libraries: name, version, licence, where
rows = {(r[3], r[0]): r for r in supply.table("Libraries")}
engine, app = supply.engine_locked(), supply.app_locked()
same("engine libraries", {n for w, n in rows if w == "engine"}, set(supply.engine_direct()))
same("app libraries", {n for w, n in rows if w == "app"}, set(supply.app_direct()))
for (where, name), (_, version, licence, _) in rows.items():
    if not licence:
        bad.append(f"libraries: {name} has no licence in NOTICE.md")
    if where == "engine" and name in engine and engine[name] != {version}:
        bad.append(f"libraries: {name} is {', '.join(sorted(engine[name]))} in uv.lock and {version} in NOTICE.md")
    if where == "app" and name in app:
        if app[name]["version"] != version:
            bad.append(f"libraries: {name} is {app[name]['version']} in package-lock.json and {version} in NOTICE.md")
        if app[name]["license"] and app[name]["license"] != licence:
            bad.append(f"libraries: {name} is {app[name]['license']} in package-lock.json and {licence} in NOTICE.md")

if bad:
    print("NOTICE.md is out of date:", *bad, sep="\n  ")
    sys.exit(1)
print(f"NOTICE.md matches the code: {len(code)} model repos, {len(rows)} libraries.")
