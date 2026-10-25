"""Walk a folder, extract units, embed them, write them to the store. Incremental."""

from __future__ import annotations

import hashlib
import os
import sys
import time
import traceback
from pathlib import Path

from .config import SKIP_DIRS, Settings
from .embedder import Embedder
from .extractors import Unit, extract, file_type
from .store import Store

try:
    from tqdm import tqdm
except ImportError:  # tqdm is optional
    def tqdm(it, **_):
        return it


def walk(root: Path, s: Settings):
    skip = SKIP_DIRS | s.extra_skip_dirs
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip
                       and not d.endswith((".app", ".photoslibrary"))]
        for fn in filenames:
            if fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            if file_type(p) is None:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size == 0 or st.st_size > s.max_file_mb * 1024 * 1024:
                continue
            yield p, st


class Indexer:
    def __init__(self, root: Path, store: Store, embedder: Embedder, s: Settings):
        self.root = root.expanduser().resolve()
        self.store, self.emb, self.s = store, embedder, s
        store.check_model(embedder.fingerprint())
        store.set_meta("root", self.root)

    def run(self, verbose: bool = True) -> dict:
        t0 = time.time()
        known = self.store.file_state()
        seen, todo = set(), []
        for p, st in walk(self.root, self.s):
            key = str(p)
            seen.add(key)
            prev = known.get(key)
            if prev is None or prev[0] != st.st_mtime or prev[1] != st.st_size:
                todo.append((p, st))
        removed = [k for k in known if k not in seen]
        for k in removed:
            self.store.remove_file(k)

        n_units = errors = 0
        # Small files first, so most of the folder is searchable quickly.
        todo.sort(key=lambda x: x[1].st_size)
        for p, st in tqdm(todo, desc="indexing", unit="file", disable=not verbose):
            n, err = self.index_file(p, st)
            n_units += n
            errors += bool(err)
            if err and verbose:
                print(f"\n  ! {p.name}: {err}", file=sys.stderr)
        return {"scanned": len(seen), "indexed": len(todo), "removed": len(removed),
                "units": n_units, "errors": errors, "seconds": round(time.time() - t0, 1)}

    def index_file(self, p: Path, st=None) -> tuple[int, str | None]:
        st = st or p.stat()
        try:
            units = list(extract(p, self.s))
            rows = self._embed(p, units)
            self.store.replace_file(str(p), file_type(p), st.st_mtime, st.st_size, rows)
            return len(rows), None
        except Exception as e:  # record the failure so we don't retry until the file changes
            msg = f"{type(e).__name__}: {e}"
            if os.environ.get("LABRADOR_DEBUG"):
                traceback.print_exc()
            self.store.replace_file(str(p), file_type(p), st.st_mtime, st.st_size, [], error=msg)
            return 0, msg

    def _embed(self, p: Path, units: list[Unit]) -> list[dict]:
        title = p.stem.replace("_", " ").replace("-", " ")
        text_units = [u for u in units if u.modality == "text"]
        img_units = [u for u in units if u.modality == "image"]

        vecs: dict[int, object] = {}
        if text_units:
            docs = [(title + (f" (page {u.page})" if u.page else ""), u.text) for u in text_units]
            for u, v in zip(text_units, self.emb.embed_documents(docs)):
                vecs[id(u)] = v
        # Page renders get a bigger vision budget than photos: they're full of small text.
        for tokens in {self.s.page_image_tokens, self.s.image_tokens}:
            batch = [u for u in img_units
                     if (self.s.page_image_tokens if u.kind == "pdf_page" else self.s.image_tokens) == tokens]
            if batch:
                for u, v in zip(batch, self.emb.embed_images([u.image for u in batch], tokens)):
                    vecs[id(u)] = v

        # Save one thumbnail per group so results can show a picture.
        media_for_group: dict[str, str] = {}
        for u in img_units:
            if u.group not in media_for_group:
                media_for_group[u.group] = self._save_media(p, u)

        rows = []
        for u in units:
            rows.append({"kind": u.kind, "modality": u.modality, "grp": u.group, "page": u.page,
                         "chunk": u.chunk, "text": u.text, "media": media_for_group.get(u.group),
                         "vec": vecs[id(u)]})
        return rows

    def _save_media(self, p: Path, u: Unit) -> str:
        h = hashlib.sha1(f"{p}|{u.group}|{u.kind}".encode()).hexdigest()[:16]
        name = f"{h}.jpg"
        im = u.image.copy()
        im.thumbnail((900, 900))
        im.save(self.store.media_dir / name, "JPEG", quality=82)
        return name
