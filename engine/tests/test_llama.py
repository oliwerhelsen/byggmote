"""The llama.cpp adapter against a stand-in for llama-server: how it is started, asked and stopped, on every platform.
The real server with a real model is in test_llama_real.py."""
import json
import sys
from pathlib import Path

import pytest

from byggmote import _alive, models

SERVER = '''import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

args = sys.argv[1:]
port, ctx = int(args[args.index("--port") + 1]), int(args[args.index("-c") + 1])


def note(obj):
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps(obj) + "\\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def answer(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.answer(200, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer " + os.environ["LLAMA_API_KEY"]:
            return self.answer(401, {"error": {"message": "Invalid API Key"}})
        if self.path == "/tokenize":
            return self.answer(200, {"tokens": [0] * int(os.environ.get("FAKE_TOKENS", "100"))})
        note({"ctx": ctx, "body": body})
        if os.environ.get("FAKE_ERROR"):
            return self.answer(400, {"error": {"message": os.environ["FAKE_ERROR"]}})
        self.answer(200, {"choices": [{"finish_reason": os.environ.get("FAKE_FINISH", "stop"),
                                       "message": {"content": "```json\\n{\\"points\\": []}\\n```"}}]})


note({"pid": os.getpid(), "args": args, "key": os.environ["LLAMA_API_KEY"]})
HTTPServer(("127.0.0.1", port), Handler).serve_forever()
'''


@pytest.fixture
def llama(tmp_path, monkeypatch):
    """The adapter with the stand-in as its server, and `said()`: what the stand-in was started with and asked."""
    script = tmp_path / "server.py"
    script.write_text(SERVER, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "log"))

    class Standin(models.LlamaServer):
        def _command(self, port: int, ctx: int) -> list[str]:  # the same arguments, to a script this Python runs
            return [sys.executable, str(script), *super()._command(port, ctx)[1:]]

    x = Standin({"id": "test"})
    x.server, x.model = Path("llama-server"), tmp_path / "model.gguf"
    return x, lambda: [json.loads(line) for line in (tmp_path / "log").read_text(encoding="utf-8").splitlines()]


def test_the_server_answers_one_prompt_and_is_gone(llama):
    x, said = llama
    assert x.summarize("Hej", {"type": "object"}) == '{"points": []}\n'
    start, asked = said()
    assert not _alive(start["pid"])
    assert asked["body"]["messages"] == [{"role": "user", "content": "Hej"}]
    assert (asked["body"]["temperature"], asked["body"]["chat_template_kwargs"]) == (0, {"enable_thinking": False})
    assert asked["body"]["response_format"]["json_schema"]["schema"] == {"type": "object"}


def test_the_server_listens_here_only_never_downloads_and_gets_its_key_unseen(llama):
    x, said = llama
    x.summarize("Hej")
    start, asked = said()
    args = " ".join(start["args"])
    assert "--host 127.0.0.1" in args and "--offline" in args and "--reasoning off" in args and "--no-webui" in args
    assert len(start["key"]) == 32 and start["key"] not in args
    assert "response_format" not in asked["body"]


def test_a_prompt_that_needs_more_context_gets_a_server_with_it(llama, monkeypatch):
    x, said = llama
    monkeypatch.setenv("FAKE_TOKENS", "20000")
    x.summarize("Hej")
    first, second, asked = said()
    assert [a["args"][a["args"].index("-c") + 1] for a in (first, second)] == ["12288", "32768"]
    assert not _alive(first["pid"]) and asked["ctx"] == 32768


def test_a_prompt_over_the_limit_is_too_long(llama, monkeypatch):
    x, _ = llama
    monkeypatch.setenv("FAKE_TOKENS", str(x.MAX_IN + 1))
    with pytest.raises(ValueError, match="too long"):
        x.summarize("Hej")


def test_what_the_server_refuses_is_passed_on(llama, monkeypatch):
    x, _ = llama
    monkeypatch.setenv("FAKE_ERROR", "JSON schema conversion failed")
    with pytest.raises(RuntimeError, match="llama-server: JSON schema conversion failed"):
        x.summarize("Hej", {"type": "object"})


def test_an_answer_cut_short_is_no_answer(llama, monkeypatch):
    x, _ = llama
    monkeypatch.setenv("FAKE_FINISH", "length")
    with pytest.raises(RuntimeError, match="did not finish"):
        x.summarize("Hej")


def test_a_server_that_does_not_start_is_an_error_not_a_wait(tmp_path):
    class Broken(models.LlamaServer):
        def _command(self, port: int, ctx: int) -> list[str]:
            return [sys.executable, "-c", "raise SystemExit(3)"]

    with pytest.raises(RuntimeError, match="llama-server stopped"):
        Broken({"id": "test"}).summarize("Hej")


def test_the_apps_own_server_comes_first(monkeypatch, tmp_path):
    monkeypatch.setenv("BYGGMOTE_LLAMA_SERVER", str(tmp_path / "llama-server"))
    assert models.llama_server() == tmp_path / "llama-server"
