"""One SQLite file per index: file records, units + vectors, and an FTS5 keyword index.

Vectors are stored as float32 blobs and searched brute-force with numpy. On an M-series
Mac a matrix product over 100k x 768 floats takes a few milliseconds, so no ANN index
is needed until you are well past a million units.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta  (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, ftype TEXT,
    mtime REAL, size INTEGER, n_units INTEGER DEFAULT 0, error TEXT, indexed_at REAL);
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    kind TEXT, modality TEXT, grp TEXT, page INTEGER, chunk INTEGER,
    text TEXT, media TEXT, vec BLOB);
CREATE INDEX IF NOT EXISTS units_file ON units(file_id);
CREATE VIRTUAL TABLE IF NOT EXISTS units_fts USING fts5(text, name, tokenize='unicode61 remove_diacritics 2');
"""


class Store:
    def __init__(self, index_dir: Path):
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.dir / "media"
        self.media_dir.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.dir / "index.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self._restrict()
        self.lock = threading.RLock()
        self._cache = None
        self._cache_ver = None

    def _restrict(self):
        """The index holds the text of private files: owner-only, re-applied on every open."""
        self.dir.chmod(0o700)
        self.media_dir.chmod(0o700)
        # SQLite creates later -wal/-shm files with the db file's mode, so chmod-ing what exists is enough.
        for suffix in ("", "-wal", "-shm"):
            f = self.dir / f"index.db{suffix}"
            if f.exists():
                f.chmod(0o600)

    # ------------------------------------------------------------ meta
    def get_meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_meta(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
            self.db.commit()

    def check_model(self, fingerprint: str):
        """Vectors from different models/dims can't be mixed in one index."""
        cur = self.get_meta("embedder")
        if cur is None:
            self.set_meta("embedder", fingerprint)
        elif cur != fingerprint:
            raise SystemExit(f"Index was built with '{cur}', not '{fingerprint}'. "
                             f"Use the same settings or `labrador index --rebuild`.")

    def _bump(self):
        v = int(self.get_meta("version", 0)) + 1
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)", (str(v),))

    # ------------------------------------------------------------ files
    def file_state(self) -> dict[str, tuple[float, int]]:
        return {p: (m, s) for p, m, s in self.db.execute("SELECT path, mtime, size FROM files")}

    def remove_file(self, path: str):
        with self.lock:
            r = self.db.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
            if not r:
                return
            self._delete_units(r[0])
            self.db.execute("DELETE FROM files WHERE id=?", (r[0],))
            self._bump()
            self.db.commit()

    def _delete_units(self, file_id: int):
        for (uid, media) in self.db.execute("SELECT id, media FROM units WHERE file_id=?", (file_id,)).fetchall():
            self.db.execute("DELETE FROM units_fts WHERE rowid=?", (uid,))
            if media:
                (self.media_dir / media).unlink(missing_ok=True)
        self.db.execute("DELETE FROM units WHERE file_id=?", (file_id,))

    def replace_file(self, path: str, ftype: str, mtime: float, size: int, rows: list[dict],
                     error: str | None = None):
        """rows: dicts with kind, modality, grp, page, chunk, text, media, vec(np.ndarray)."""
        import time
        name = Path(path).name
        with self.lock:
            r = self.db.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
            if r:
                fid = r[0]
                self._delete_units(fid)
                self.db.execute("UPDATE files SET ftype=?, mtime=?, size=?, n_units=?, error=?, indexed_at=? WHERE id=?",
                                (ftype, mtime, size, len(rows), error, time.time(), fid))
            else:
                fid = self.db.execute(
                    "INSERT INTO files(path, ftype, mtime, size, n_units, error, indexed_at) VALUES (?,?,?,?,?,?,?)",
                    (path, ftype, mtime, size, len(rows), error, time.time())).lastrowid
            for row in rows:
                uid = self.db.execute(
                    "INSERT INTO units(file_id, kind, modality, grp, page, chunk, text, media, vec) VALUES (?,?,?,?,?,?,?,?,?)",
                    (fid, row["kind"], row["modality"], row["grp"], row["page"], row["chunk"], row["text"],
                     row["media"], np.asarray(row["vec"], np.float32).tobytes())).lastrowid
                # Keyword index: text units by content; every unit also by file name.
                self.db.execute("INSERT INTO units_fts(rowid, text, name) VALUES (?,?,?)",
                                (uid, row["text"] if row["modality"] == "text" else "", _name_words(name)))
            self._bump()
            self.db.commit()

    # ------------------------------------------------------------ search support
    def matrix(self):
        """(unit_ids, modalities, vectors) cached until the index changes."""
        ver = self.get_meta("version", "0")
        if self._cache is None or self._cache_ver != ver:
            rows = self.db.execute("SELECT id, modality, vec FROM units").fetchall()
            if rows:
                ids = np.array([r[0] for r in rows], np.int64)
                mods = np.array([r[1] for r in rows])
                M = np.frombuffer(b"".join(r[2] for r in rows), np.float32).reshape(len(rows), -1)
            else:
                ids, mods, M = np.zeros(0, np.int64), np.array([]), np.zeros((0, 1), np.float32)
            self._cache, self._cache_ver = (ids, mods, M), ver
        return self._cache

    def keyword(self, query: str, limit: int = 200) -> list[int]:
        words = re.findall(r"\w+", query.lower())
        words = [w for w in words if len(w) > 1]
        if not words:
            return []
        # AND, not OR: OR lets common words match nearly every text unit, and that noise outranks
        # pictures and other-language files in the fusion. AND fires mostly on short, specific
        # queries (IDs, codes, names), which is where keywords beat embeddings.
        q = " AND ".join(f'"{w}"' for w in words)
        try:
            return [r[0] for r in self.db.execute(
                "SELECT rowid FROM units_fts WHERE units_fts MATCH ? ORDER BY bm25(units_fts, 1.0, 0.5) LIMIT ?",
                (q, limit))]
        except sqlite3.OperationalError:
            return []

    def units(self, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        cur = self.db.execute(
            f"SELECT u.id, u.file_id, f.path, f.ftype, u.kind, u.modality, u.grp, u.page, u.chunk, u.text, u.media "
            f"FROM units u JOIN files f ON f.id=u.file_id WHERE u.id IN ({q})", ids)
        cols = ["id", "file_id", "path", "ftype", "kind", "modality", "grp", "page", "chunk", "text", "media"]
        return {r[0]: dict(zip(cols, r)) for r in cur}

    def files_meta(self, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        cur = self.db.execute(f"SELECT id, path, mtime FROM files WHERE id IN ({q})", list(ids))
        return {r[0]: {"path": r[1], "mtime": r[2]} for r in cur}

    def group_units(self, file_id: int, grp: str) -> list[dict]:
        cur = self.db.execute("SELECT id, kind, modality, text, media FROM units WHERE file_id=? AND grp=? ORDER BY chunk, id",
                              (file_id, grp))
        return [dict(zip(["id", "kind", "modality", "text", "media"], r)) for r in cur]

    def stats(self) -> dict:
        f = self.db.execute("SELECT ftype, COUNT(*) FROM files GROUP BY ftype").fetchall()
        u = self.db.execute("SELECT kind, COUNT(*) FROM units GROUP BY kind").fetchall()
        errs = self.db.execute("SELECT COUNT(*) FROM files WHERE error IS NOT NULL").fetchone()[0]
        return {"files": dict(f), "units": dict(u), "errors": errs,
                "embedder": self.get_meta("embedder"), "root": self.get_meta("root"),
                "index_dir": str(self.dir)}


def _name_words(name: str) -> str:
    """'Q3_invoice-2024.pdf' -> 'Q3 invoice 2024 pdf' so file names are keyword-searchable."""
    return re.sub(r"[_\-.]+", " ", name)
