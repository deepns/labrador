"""Web hardening: index permissions, Host/Origin checks, security headers, CSP-safe static UI.

    uv run --extra dev pytest -q tests/test_web.py
"""

import os
import re
import stat

import pytest
from PIL import Image
from starlette.testclient import TestClient

from labrador import cli
from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.indexer import Indexer
from labrador.store import Store
from labrador.web import create_app


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("The lease allows dogs in the apartment.")
    (folder / "b.txt").write_text("Quarterly revenue grew by ten percent.")
    Image.new("RGB", (64, 64), "red").save(folder / "c.png")
    s = Settings(backend="fake")
    emb = load_embedder(s)
    store = Store(tmp_path / "idx")
    Indexer(folder, store, emb, s).run()
    return store, emb


def _mode(p):
    return stat.S_IMODE(p.stat().st_mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_index_permissions(tmp_path):
    idx = tmp_path / "idx"
    Store(idx)
    assert _mode(idx) == 0o700 and _mode(idx / "media") == 0o700 and _mode(idx / "index.db") == 0o600
    idx.chmod(0o755)
    (idx / "media").chmod(0o755)
    (idx / "index.db").chmod(0o644)
    Store(idx)
    assert _mode(idx) == 0o700 and _mode(idx / "media") == 0o700 and _mode(idx / "index.db") == 0o600


def test_host_check(env):
    app = create_app(*env)
    assert TestClient(app, base_url="http://evil.example").get("/api/stats").status_code == 400
    assert TestClient(app, base_url="http://127.0.0.1:8765").get("/api/stats").status_code == 200
    assert TestClient(app, base_url="http://localhost").get("/api/stats").status_code == 200
    v6 = create_app(*env, allowed_hosts={"127.0.0.1", "localhost", "::1"})
    assert TestClient(v6, base_url="http://[::1]:8765").get("/api/stats").status_code == 200
    assert TestClient(app, base_url="http://LOCALHOST:8765").get("/api/stats").status_code == 200
    lan = create_app(*env, allowed_hosts={"*"})
    assert TestClient(lan, base_url="http://evil.example").get("/api/stats").status_code == 200


def test_origin_check(env, monkeypatch):
    monkeypatch.setattr("labrador.web.subprocess.Popen", lambda *a, **k: None)   # never open Finder
    c = TestClient(create_app(*env), base_url="http://localhost:8765")
    fid = env[0].db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
    assert c.post(f"/reveal/{fid}", headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post(f"/reveal/{fid}", headers={"Origin": "null"}).status_code == 403
    assert c.post(f"/reveal/{fid}", headers={"Origin": "http://localhost:8765"}).status_code == 200
    assert c.post(f"/reveal/{fid}").status_code == 200   # no Origin: non-browser client


def test_security_headers(env):
    c = TestClient(create_app(*env), base_url="http://localhost")
    for url in ("/", "/api/search?q=x", "/static/app.js"):
        r = c.get(url)
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert c.get("/").headers["cache-control"] == "no-store"
    assert c.get("/api/search?q=x").headers["cache-control"] == "no-store"
    media = env[0].db.execute("SELECT media FROM units WHERE media IS NOT NULL LIMIT 1").fetchone()
    assert media, "png should have produced a media file"
    assert c.get(f"/media/{media[0]}").headers["cache-control"] == "max-age=3600"


def test_static_ui_is_csp_safe(env):
    c = TestClient(create_app(*env), base_url="http://localhost")
    assert c.get("/static/app.js").status_code == 200 and c.get("/static/app.css").status_code == 200
    html = c.get("/").text
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html)
    assert "onclick=" not in html and "style=" not in html
    assert "onclick=" not in c.get("/static/app.js").text and "style=" not in c.get("/static/app.js").text


def test_serve_refuses_lan_without_flag(monkeypatch):
    monkeypatch.setattr(cli, "_open", lambda a: pytest.fail("loaded the index"))
    with pytest.raises(SystemExit) as e:
        cli.main(["serve", "--host", "0.0.0.0"])
    assert e.value.code not in (0, None)


def test_serve_hosts():
    ns = lambda host, lan=False: type("A", (), {"host": host, "allow_lan": lan})()  # noqa: E731
    assert cli._serve_hosts(ns("::1")) == {"127.0.0.1", "localhost", "::1"}
    assert cli._serve_hosts(ns("0.0.0.0", True)) == {"*"}
    assert cli._serve_hosts(ns("192.168.1.5", True)) == {"127.0.0.1", "localhost", "192.168.1.5"}
    with pytest.raises(SystemExit):
        cli._serve_hosts(ns("myhost.local"))
