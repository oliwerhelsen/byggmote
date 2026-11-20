"""The real llama-server with a real model, small or large: that this platform's build starts with the arguments the
adapter gives it, holds an answer to a schema and is gone afterwards. Slow, and only where BYGGMOTE_TEST_GGUF names a
model file: `BYGGMOTE_TEST_GGUF=model.gguf uv run pytest -m slow -n 0`."""
import json
import os
import socket
from pathlib import Path

import pytest

from byggmote import models

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not os.environ.get("BYGGMOTE_TEST_GGUF"), reason="BYGGMOTE_TEST_GGUF names no model")]

# What the protocol's own schema uses: a number and a text among a few, a text or nothing, a date's pattern.
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["heading", "role", "due", "quote"], "properties": {
    "heading": {"type": "integer", "enum": [3, 4]},
    "role": {"anyOf": [{"type": "string", "enum": ["Platschef", "Beställarens ombud"]}, {"type": "null"}]},
    "due": {"anyOf": [{"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}, {"type": "null"}]},
    "quote": {"type": "string", "maxLength": 80}}}
PROMPT = """Dagordningens rubriker:
3. Tidplan
4. Ekonomi

Utskrift:
[00:44] Anders: Beställaren godkänner ÄTA 14 till fast pris 86 500 kr.

Vilken rubrik hör det till, vilken Roll ansvarar och vad sägs ordagrant? Svara med ett JSON-objekt.
"""


def test_the_real_server_holds_an_answer_to_a_schema_and_is_gone():
    class Seen(models.LlamaServer):
        def _command(self, port: int, ctx: int) -> list[str]:
            self.port = port
            return super()._command(port, ctx)

    x = Seen({"id": "test"})
    x.server, x.model = models.llama_server(), Path(os.environ["BYGGMOTE_TEST_GGUF"]).resolve()
    got = json.loads(x.summarize(PROMPT, SCHEMA))
    assert set(got) == set(SCHEMA["required"])
    assert got["heading"] in (3, 4) and got["role"] in ("Platschef", "Beställarens ombud", None)
    assert isinstance(got["quote"], str) and len(got["quote"]) <= 80
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", x.port), timeout=2).close()
