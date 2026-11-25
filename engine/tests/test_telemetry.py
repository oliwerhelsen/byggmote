"""pyannote's telemetry stays off wherever the engine starts (docs/security.md)."""
import os
import subprocess
import sys
from pathlib import Path


def test_importing_the_engine_switches_pyannote_telemetry_off():
    # Even when the person's environment asks for it: the engine does not.
    code = "import os, byggmote; print(os.environ.get('PYANNOTE_METRICS_ENABLED'))"
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYANNOTE_METRICS_ENABLED": "true"}, capture_output=True, text=True)
    assert out.stdout.strip() == "false", out.stderr


def test_the_test_run_itself_has_it_off():
    import byggmote  # noqa: F401
    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "false"


def test_the_app_hands_it_to_every_engine_it_starts():
    ts = (Path(__file__).parents[2] / "app" / "src" / "main" / "engine.ts").read_text()
    assert "PYANNOTE_METRICS_ENABLED: 'false'" in ts
