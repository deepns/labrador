"""Small local web UI (Starlette). Binds to 127.0.0.1 only; serves only files that are in the index.

A pure-ASGI middleware adds the browser protections: Host allow-list (blocks DNS rebinding), Origin check on
unsafe methods (blocks cross-site POSTs), and CSP / nosniff / no-referrer / no-store headers on every response.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

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


def create_app(store, emb, allowed_hosts=None):
    model_lock = threading.Lock()   # one model, one inference at a time (MPS isn't re-entrant)

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
        Route("/api/stats", api_stats),
        Route("/media/{name}", media),
        Route("/file/{fid:int}", original),
        Route("/reveal/{fid:int}", reveal, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC)),
    ], middleware=[Middleware(WebGuard, allowed_hosts=allowed_hosts or ("127.0.0.1", "localhost"))])
