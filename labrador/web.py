"""Small local web UI (Starlette). Binds to 127.0.0.1 only; serves only files that are in the index."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .search import search

STATIC = Path(__file__).parent / "static"


def create_app(store, emb):
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
    ])
