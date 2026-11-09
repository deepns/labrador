"""LLM client tests: no network, no model. HTTP is faked with httpx.MockTransport, DNS by monkeypatching."""

import json
import os
import socket
import subprocess
import sys

import httpx
import pytest

from labrador import llm as llm_mod
from labrador.config import Settings
from labrador.llm import FakeLLM, LLMError, OpenAICompatLLM, load_llm, require_loopback

MSGS = [{"role": "user", "content": "hi"}]


def resolve_to(monkeypatch, *addrs):
    def fake(host, port, **kw):
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port))
                for a in addrs]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


def make(handler, **kw):
    return OpenAICompatLLM("http://127.0.0.1:11434/v1", "m", extra={"keep_alive": "2m"},
                           transport=httpx.MockTransport(handler), **kw)


def test_loopback_accepts(monkeypatch):
    require_loopback("http://127.0.0.1:11434/v1")
    require_loopback("http://[::1]:8080/v1")
    resolve_to(monkeypatch, "127.0.0.1", "::1")
    require_loopback("http://localhost:11434/v1")


@pytest.mark.parametrize("url", ["http://10.0.0.5:11434/v1", "http://192.168.1.2/v1", "/v1", "http:///v1",
                                 "http://127.0.0.1:99999/v1", "http://127.0.0.1:abc/v1",
                                 "ftp://127.0.0.1/v1"])
def test_loopback_rejects(url):
    with pytest.raises(LLMError):
        require_loopback(url)


def test_loopback_rejects_hostnames(monkeypatch):
    resolve_to(monkeypatch, "8.8.8.8")
    with pytest.raises(LLMError, match="allow-remote-llm"):
        require_loopback("http://llm.example.com/v1")
    resolve_to(monkeypatch, "127.0.0.1", "8.8.8.8")
    with pytest.raises(LLMError, match="8.8.8.8"):
        require_loopback("http://sneaky.example.com/v1")

    def boom(*a, **kw):
        raise socket.gaierror("nope")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(LLMError, match="resolve"):
        require_loopback("http://nowhere.invalid/v1")


def test_malformed_responses_raise_llm_error():
    bad_sse = make(lambda req: httpx.Response(200, content=b"data: {not json\n\n"))
    with pytest.raises(LLMError, match="can't parse"):
        list(bad_sse.stream(MSGS))
    oops = make(lambda req: httpx.Response(200, json={"oops": 1}))
    with pytest.raises(LLMError, match="can't parse"):
        oops.complete(MSGS)

    def read_error(req):
        raise httpx.ReadError("connection reset")
    with pytest.raises(LLMError, match="failed"):
        make(read_error).complete(MSGS)


def test_stream_parses_sse():
    seen = {}
    sse = (b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
           b': keep-alive\n\n'
           b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
           b'data:{"choices":[{"delta":{"content":"lo "}}]}\n'
           b'\n'
           b'data: {"choices":[{"delta":{"content":null}}]}\n\n'
           b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
           b'data: {"choices":[],"usage":{"total_tokens":5}}\n\n'
           b'data: [DONE]\n\n'
           b'data: not json at all\n\n')

    def handler(req):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    assert "".join(make(handler).stream(MSGS)) == "Hello world"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["stream"] is True and seen["body"]["temperature"] == 0.0
    assert seen["body"]["model"] == "m" and seen["body"]["keep_alive"] == "2m"
    assert seen["body"]["messages"] == MSGS


def test_stream_error_chunk():
    sse = b'data: {"choices":[{"delta":{"content":"a"}}]}\n\ndata: {"error":{"message":"out of memory"}}\n\n'
    with pytest.raises(LLMError, match="out of memory"):
        list(make(lambda req: httpx.Response(200, content=sse)).stream(MSGS))


def test_complete_with_and_without_schema():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    c = make(handler)
    assert c.complete(MSGS) == "ok"
    assert c.complete(MSGS, schema={"type": "object"}) == "ok"
    assert "response_format" not in bodies[0] and bodies[0]["stream"] is False
    assert bodies[1]["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "answer", "schema": {"type": "object"}, "strict": True}}


def test_http_errors():
    c = make(lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(LLMError, match="500"):
        c.complete(MSGS)
    with pytest.raises(LLMError, match="500"):
        list(c.stream(MSGS))

    def refuse(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(LLMError, match="127.0.0.1:11434"):
        make(refuse).complete(MSGS)

    def slow(req):
        raise httpx.ReadTimeout("slow")
    with pytest.raises(LLMError, match="timed out"):
        make(slow).complete(MSGS)


def test_models():
    c = make(lambda req: httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b-cloud"}]}))
    assert c.models() == ["a", "b-cloud"]


def test_fake_llm():
    f = FakeLLM(["abcdefgh", "second"], chunk=3)
    pieces = list(f.stream(MSGS))
    assert "".join(pieces) == "abcdefgh" and all(len(p) <= 3 for p in pieces)
    assert f.complete(MSGS) == "second"
    assert f.complete(MSGS) == "second"
    assert f.calls == [MSGS] * 3
    assert "".join(FakeLLM().stream(MSGS)) == "This is a fake answer [1]."


def test_load_llm(monkeypatch, capsys):
    assert isinstance(load_llm(Settings(llm_url="fake")), FakeLLM)
    assert isinstance(load_llm(Settings(llm_url="http://127.0.0.1:11434/v1")), OpenAICompatLLM)
    remote = Settings(llm_url="http://10.0.0.5:11434/v1")
    with pytest.raises(LLMError):
        load_llm(remote)
    remote.allow_remote_llm = True
    assert isinstance(load_llm(remote), OpenAICompatLLM)
    assert "http://10.0.0.5:11434/v1" in capsys.readouterr().err
    assert llm_mod.OpenAICompatLLM(remote.llm_url, "m").client.trust_env is False


def test_llm_url_env_override():
    code = "from labrador.config import Settings; print(Settings().llm_url)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={**os.environ, "LABRADOR_LLM_URL": "http://127.0.0.1:1/v1"})
    assert out.stdout.strip() == "http://127.0.0.1:1/v1"
