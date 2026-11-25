#!/usr/bin/env python3
"""A software bill of materials (CycloneDX 1.5, JSON) on standard output: `python3 scripts/sbom.py [version] > sbom.cdx.json`.

What is in it: every package in `engine/uv.lock` (all three platforms' wheels in one list) and in `app/package-lock.json`,
and the models `models.py` fetches, each at its commit. A licence is given where a source states it: the npm lock, and
NOTICE.md for the libraries it lists. What is not in it: `ffmpeg` and `llama-server`, which this repo neither ships nor
pins (NOTICE.md), and the Python interpreter. Hashes are left out: the locks hold them per file."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
import supply  # noqa: E402


def licence(name: str) -> list[dict]:
    return [{"license": {"name": name}}] if name else []


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "0.1.0"
    noted = {(r[3], r[0]): r[2] for r in supply.table("Libraries")}
    parts = []
    for name, versions in sorted(supply.engine_locked().items()):
        for v in sorted(versions):
            parts.append({"type": "library", "bom-ref": f"pypi/{name}@{v}", "name": name, "version": v, "purl": f"pkg:pypi/{name}@{v}",
                          "licenses": licence(noted.get(("engine", name), "")), "properties": [{"name": "byggmote:part", "value": "engine"}]})
    for name, p in sorted(supply.app_locked().items()):
        ns, _, base = name.rpartition("/")
        purl = f"pkg:npm/{quote(ns)}/{base}@{p['version']}" if ns else f"pkg:npm/{base}@{p['version']}"
        parts.append({"type": "library", "bom-ref": f"npm/{name}@{p['version']}", "name": name, "version": p["version"], "purl": purl,
                      "licenses": licence(p["license"]), "properties": [{"name": "byggmote:part", "value": "app"}]})
    for repo, (commit, lic) in sorted(supply.models().items()):
        parts.append({"type": "machine-learning-model", "bom-ref": f"huggingface/{repo}@{commit}", "name": repo, "version": commit,
                      "purl": f"pkg:huggingface/{repo}@{commit}", "licenses": licence(lic),
                      "properties": [{"name": "byggmote:part", "value": "model, fetched to the computer at first use, not shipped"}]})
    bom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "component": {"type": "application", "bom-ref": "byggmote", "name": "Byggmöte", "version": version}},
        "components": parts,
    }
    json.dump(bom, sys.stdout, ensure_ascii=False, indent=1)
    print()


main()
