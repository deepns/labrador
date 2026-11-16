"""Small local web UI (Starlette). Binds to 127.0.0.1 only; serves only files that are in the index.

`POST /api/ask` (JSON body, application/json only) streams answer.ask() events as NDJSON, one per line. The server
masks identifiers (the `done` event's unverified tokens too) and sends each as {"mask", "raw"}; the page shows `mask`
and swaps in `raw` on click, so masking rules live only in answer.py. The model_lock covers retrieval, never generation.

A pure-ASGI middleware adds the browser protections: Host allow-list (blocks DNS rebinding), Origin check on
unsafe methods (blocks cross-site POSTs), and CSP / nosniff / no-referrer / no-store headers on every response.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import threading
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .answer import ask, mask_text
from .config import Settings
from .search import search

STATIC = Path(__file__).parent / "static"


# Applied to every response, /file/{fid} included on purpose: an indexed .html file opened from the UI
# must not run scripts on labrador's origin.
SECURITY_HEADERS = {
    "content-security-policy": "default-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


class WebGuard:
    """Pure ASGI (no BaseHTTPMiddleware) so streamed responses pass through untouched."""

    def __init__(self, app, allowed_hosts=("127.0.0.1", "localhost")):
        self.app = app
        self.allowed_hosts = {h.lower() for h in allowed_hosts}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        h = Headers(scope=scope)
        host = h.get("host", "").lower()
        hostname = host.rsplit(":", 1)[0] if not host.endswith("]") and ":" in host else host
        if "*" not in self.allowed_hosts and hostname.strip("[]") not in self.allowed_hosts:
            return await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
        origin = h.get("origin")
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and origin is not None \
                and origin.lower().split("://", 1)[-1] != host:
            return await PlainTextResponse("Cross-origin request refused", status_code=403)(scope, receive, send)

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                hdrs = Headers(raw=msg["headers"])
                extra = dict(SECURITY_HEADERS)
                if "cache-control" not in hdrs:
                    extra["cache-control"] = "no-store"
                msg["headers"] = [*msg["headers"], *((k.encode(), v.encode()) for k, v in extra.items())]
            await send(msg)

        await self.app(scope, receive, send_with_headers)


class LockedEmbedder:
    """Takes the lock around each embedding call. ask() interleaves retrieval and generation (and retries by
    retrieving again), so the lock can't wrap the whole generator: a slow answer would block every search."""

    def __init__(self, emb, lock):
        self._emb, self._lock = emb, lock

    def __getattr__(self, name):
        attr = getattr(self._emb, name)
        if not name.startswith("embed_"):
            return attr

        def locked(*a, **kw):
            with self._lock:
                return attr(*a, **kw)
        return locked


def _mask_token(tok: str):
    segs = mask_text(tok)
    if all(isinstance(x, str) for x in segs):
        return tok
    return {"mask": "".join(x if isinstance(x, str) else x["mask"] for x in segs), "raw": tok}


def _ndjson(events):
    try:
        for e in events:
            if e["type"] == "done":
                e = {**e, "check": {**e["check"], "unverified": [_mask_token(t) for t in e["check"]["unverified"]]}}
            yield json.dumps(e, ensure_ascii=False) + "\n"
    except Exception:       # no tracebacks to the browser
        yield json.dumps({"type": "error", "message": "Something went wrong while answering."}) + "\n"


def create_app(store, emb, allowed_hosts=None, llm=None, settings=None):
    model_lock = threading.Lock()   # one model, one inference at a time (MPS isn't re-entrant)
    settings = settings or Settings()

    def _search(q, k, only):
        with model_lock:
            return [h.to_dict() for h in search(store, emb, q, k=k, only=only)]

    async def index(_):
        return HTMLResponse((STATIC / "index.html").read_text())

    async def api_search(req):
        q = req.query_params.get("q", "").strip()
        if not q:
            return JSONResponse([])
        k = min(int(req.query_params.get("k", 24)), 100)
        only = req.query_params.get("only") or None
        return JSONResponse(await run_in_threadpool(_search, q, k, only))

    async def api_ask(req):
        if req.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return PlainTextResponse("Send JSON with content-type: application/json", status_code=415)
        try:
            body = await req.json()
        except ValueError:
            body = None
        q = body.get("q") if isinstance(body, dict) else None
        k = body.get("k", settings.ask_sources) if isinstance(body, dict) else None
        if not isinstance(q, str) or not q.strip() or isinstance(k, bool) or not isinstance(k, int):
            return PlainTextResponse("Expected a JSON object with a non-empty string q (and an integer k)",
                                     status_code=400)
        images = body.get("images", False)
        if not isinstance(images, bool):
            return PlainTextResponse("images must be true or false", status_code=400)
        if llm is None:
            return PlainTextResponse("No LLM configured; restart `labrador serve` with --llm-url or --model",
                                     status_code=503)
        k = max(1, min(k, 20))
        s = dataclasses.replace(settings, ask_sources=k, ask_search_k=max(settings.ask_search_k, k),
                                ask_images=2 if images else 0)
        events = ask(store, LockedEmbedder(emb, model_lock), llm, q.strip(), s, reveal=False)
        return StreamingResponse(_ndjson(events), media_type="application/x-ndjson")

    async def api_stats(_):
        return JSONResponse(store.stats())

    async def media(req):
        name = req.path_params["name"]
        ok = store.db.execute("SELECT 1 FROM units WHERE media=? LIMIT 1", (name,)).fetchone()
        p = store.media_dir / name
        if not ok or not p.exists():
            return Response(status_code=404)
        return FileResponse(p, headers={"Cache-Control": "max-age=3600"})

    def _path(fid: int) -> Path | None:
        r = store.db.execute("SELECT path FROM files WHERE id=?", (fid,)).fetchone()
        return Path(r[0]) if r and Path(r[0]).exists() else None

    async def original(req):
        p = _path(int(req.path_params["fid"]))
        return FileResponse(p) if p else Response(status_code=404)

    async def reveal(req):
        p = _path(int(req.path_params["fid"]))
        if not p:
            return Response(status_code=404)
        if sys.platform == "darwin":
            if req.query_params.get("mode") == "open":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["open", "-R", str(p)])   # show in Finder
        return JSONResponse({"ok": True, "path": str(p)})

    return Starlette(routes=[
        Route("/", index),
        Route("/api/search", api_search),
        Route("/api/ask", api_ask, methods=["POST"]),
        Route("/api/stats", api_stats),
        Route("/media/{name}", media),
        Route("/file/{fid:int}", original),
        Route("/reveal/{fid:int}", reveal, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC)),
    ], middleware=[Middleware(WebGuard, allowed_hosts=allowed_hosts or ("127.0.0.1", "localhost"))])
