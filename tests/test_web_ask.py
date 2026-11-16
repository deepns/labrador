"""POST /api/ask: NDJSON stream, server-side masking, request validation, lock scope. Fake embedder + FakeLLM."""

import json
import threading

import pytest
from starlette.testclient import TestClient

from labrador import cli
from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.indexer import Indexer
from labrador.llm import LLM, FakeLLM, LLMError
from labrador.store import Store
from labrador.web import create_app

JSON = {"content-type": "application/json"}


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "passport.txt").write_text("Passport of Anna Eriksson\nPassport number L898902C3\n")
    s = Settings(backend="fake")
    emb = load_embedder(s)
    store = Store(tmp_path / "idx")
    Indexer(folder, store, emb, s).run()
    return store, emb


def client(env, llm, **kw):
    return TestClient(create_app(*env, llm=llm, **kw), base_url="http://localhost")


def ask(c, q="passport number", **body):
    r = c.post("/api/ask", json={"q": q, **body})
    return r, [json.loads(l) for l in r.text.splitlines()] if r.status_code == 200 else []


def test_stream_order_and_headers(env):
    r, ev = ask(client(env, FakeLLM(["The number is fine [1]."])))
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.headers["cache-control"] == "no-store" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    types = [e["type"] for e in ev]
    assert types[0] == "sources" and types[-1] == "done" and set(types[1:-1]) == {"delta"}
    assert ev[0]["sources"][0]["rel_path"] == "passport.txt"
    assert "".join(e["text"] for e in ev if e["type"] == "delta") == "The number is fine [1]."
    assert ev[-1]["check"]["citations"] == [1] and ev[-1]["retried"] is False


def test_masked_segment_has_mask_and_raw(env):
    _, ev = ask(client(env, FakeLLM(["Your passport number is L898902C3 [1]."])), k=3)
    m = [e for e in ev if e["type"] == "delta" and "mask" in e]
    assert m == [{"type": "delta", "mask": "•••••02C3", "raw": "L898902C3"}]


def test_unverified_tokens_are_masked_segments(env):
    _, ev = ask(client(env, FakeLLM(["Your passport number is L898902C4 [1]."])))
    assert ev[-1]["check"]["unverified"] == [{"mask": "•••••02C4", "raw": "L898902C4"}]


def test_plain_unverified_token_stays_a_string(env):
    _, ev = ask(client(env, FakeLLM(["It expires on 2031-01-01 [1]."])))
    assert ev[-1]["check"]["unverified"] == ["2031-01-01"]


def test_retry_event(env):
    _, ev = ask(client(env, FakeLLM(["I couldn't find that in your files.", "Number L898902C3 [1]."])),
                q="what is the passport number for Anna")
    assert "retry" in [e["type"] for e in ev] and ev[-1]["retried"] is True


def test_llm_error_becomes_error_event(env):
    class Boom(FakeLLM):
        def stream(self, messages):
            raise LLMError("runtime is down")
            yield
    _, ev = ask(client(env, Boom()))
    assert ev[-1] == {"type": "error", "message": "runtime is down"}


def test_unexpected_exception_hides_traceback(env):
    class Bug(FakeLLM):
        def stream(self, messages):
            raise ValueError("secret detail")
            yield
    _, ev = ask(client(env, Bug()))
    assert ev[-1]["type"] == "error" and "secret" not in json.dumps(ev[-1])


def test_request_validation(env):
    c = client(env, FakeLLM())
    assert c.post("/api/ask", content='{"q": "x"}', headers={"content-type": "text/plain"}).status_code == 415
    assert c.post("/api/ask", content='{"q": "x"}').status_code == 415
    assert c.post("/api/ask", content="nope", headers=JSON).status_code == 400
    assert c.post("/api/ask", json=["x"]).status_code == 400
    assert c.post("/api/ask", json={"q": "  "}).status_code == 400
    assert c.post("/api/ask", json={"q": "x", "k": "5"}).status_code == 400
    assert c.post("/api/ask", json={"q": "x", "images": "yes"}).status_code == 400
    assert c.post("/api/ask", json={"q": "x", "images": True}).status_code == 200
    assert c.post("/api/ask", json={"q": "x", "k": 999}).status_code == 200      # clamped, not refused
    assert c.get("/api/ask").status_code == 405


def test_no_llm_is_503(env):
    assert TestClient(create_app(*env), base_url="http://localhost").post("/api/ask", json={"q": "x"}).status_code == 503


def test_cross_origin_post_refused(env):
    r = client(env, FakeLLM()).post("/api/ask", json={"q": "x"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_k_is_clamped_and_applied(env, monkeypatch):
    seen = []
    monkeypatch.setattr("labrador.web.ask", lambda store, emb, llm, q, s, reveal: seen.append(s) or iter([]))
    c = client(env, FakeLLM(), settings=Settings(ask_search_k=10, ask_sources=5))
    for body in ({}, {"k": 0}, {"k": 3}, {"k": 99}):
        c.post("/api/ask", json={"q": "x", **body})
    assert [(s.ask_sources, s.ask_search_k) for s in seen] == [(5, 10), (1, 10), (3, 10), (20, 20)]


def test_model_lock_not_held_during_generation(env, monkeypatch):
    held = []

    class Probe(LLM):
        def stream(self, messages):
            held.append(lock.locked())
            yield "Fine [1]."

    real = threading.Lock
    created = []
    monkeypatch.setattr("labrador.web.threading.Lock", lambda: created.append(real()) or created[-1])
    c = client(env, Probe())
    lock = created[0]
    _, ev = ask(c)
    assert ev[-1]["type"] == "done" and held == [False]
    assert not lock.locked()


def test_serve_llm_flags_parse_and_remote_url_exits_early(monkeypatch):
    a = cli.build_parser().parse_args(["serve", "--llm-url", "fake", "--model", "m", "--ctx", "2048",
                                       "--llm-extra", "{}", "--allow-remote-llm"])
    assert a.llm_url == "fake" and a.ctx == 2048 and a.allow_remote_llm
    monkeypatch.setattr(cli, "_open", lambda *a, **k: pytest.fail("loaded the embedder"))
    monkeypatch.setattr("labrador.llm.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 80))])
    with pytest.raises(SystemExit) as e:
        cli.main(["serve", "--llm-url", "http://example.com/v1"])
    assert "not loopback" in str(e.value.code)


def test_images_flag_reaches_the_prompt(env, tmp_path):
    from PIL import Image
    store, emb = env
    folder = tmp_path / "docs"
    Image.new("RGB", (64, 64), "white").save(folder / "scan.png")
    Indexer(folder, store, emb, Settings(backend="fake")).run()
    llm = FakeLLM()
    _, ev = ask(client(env, llm), images=True)
    assert any(x["picture"] for x in ev[0]["sources"])
    assert any(p["type"] == "image_url" for p in llm.calls[0][1]["content"])
    llm2 = FakeLLM()
    ask(client(env, llm2), images=False)
    assert isinstance(llm2.calls[0][1]["content"], str)
