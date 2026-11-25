"""What Byggmöte is made of, read from the files that decide it. Shared by check-notice.py and sbom.py. Python 3.11+, standard library only."""
import ast
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def models() -> dict[str, tuple[str, str]]:
    """{repo: (commit, licence)} for every model engine/src/byggmote/models.py can fetch, its extra files' repos included."""
    tree = ast.parse((ROOT / "engine/src/byggmote/models.py").read_text(encoding="utf-8"))
    consts = {n.targets[0].id: n.value.value for n in tree.body
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}

    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return consts.get(n.id)
        if isinstance(n, ast.Tuple):
            return tuple(ev(x) for x in n.elts)

    found: dict[str, tuple[str, str]] = {}
    for d in (n for n in ast.walk(tree) if isinstance(n, ast.Dict)):
        e = {ev(k): ev(v) for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant)}
        if "model" in e and "revision" in e:
            found.setdefault(e["model"], (e["revision"], e["license"]))
            if e.get("extra"):
                found.setdefault(e["extra"][0], (e["extra"][2], e["license"]))
    return found


def engine_direct() -> list[str]:
    """The engine's own dependencies (not the dev group), as normalised names."""
    p = tomllib.loads((ROOT / "engine/pyproject.toml").read_text(encoding="utf-8"))["project"]
    specs = p["dependencies"] + [s for extra in p.get("optional-dependencies", {}).values() for s in extra]
    return sorted({norm(re.match(r"[A-Za-z0-9_.-]+", s).group()) for s in specs})


def engine_locked() -> dict[str, set[str]]:
    """{name: {versions}} from uv.lock, one version per platform at most."""
    out: dict[str, set[str]] = {}
    for p in tomllib.loads((ROOT / "engine/uv.lock").read_text(encoding="utf-8"))["package"]:
        if p["name"] != "byggmote":
            out.setdefault(norm(p["name"]), set()).add(p["version"])
    return out


def app_direct() -> list[str]:
    j = json.loads((ROOT / "app/package.json").read_text(encoding="utf-8"))
    return sorted({*j.get("dependencies", {}), *j.get("devDependencies", {})})


def app_locked() -> dict[str, dict]:
    """{name: {"version", "license"}} from package-lock.json."""
    out = {}
    for path, p in json.loads((ROOT / "app/package-lock.json").read_text(encoding="utf-8"))["packages"].items():
        if path.startswith("node_modules/") and path.count("node_modules/") == 1:  # the top level: what package.json named
            out[path.removeprefix("node_modules/")] = {"version": p["version"], "license": p.get("license", "")}
    return out


def table(heading: str) -> list[list[str]]:
    """The rows of the first table under the heading in NOTICE.md, cells stripped of spaces and backticks."""
    lines = (ROOT / "NOTICE.md").read_text(encoding="utf-8").splitlines()
    i = next((n for n, l in enumerate(lines) if re.match(r"#{2,3} " + re.escape(heading) + r"\s*$", l)), None)
    if i is None:
        raise SystemExit(f"NOTICE.md has no heading '{heading}'")
    rows = []
    for l in lines[i + 1:]:
        if l.startswith("#"):
            break
        if l.startswith("|"):
            cells = [c.strip().strip("`") for c in l.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                rows.append(cells)
    return rows[1:]  # without the header
