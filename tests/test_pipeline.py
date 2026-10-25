"""End-to-end plumbing test with the fake embedder (no model download).

    uv run --extra dev pytest -q
"""

import subprocess
import sys
from pathlib import Path

from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.extractors import chunk_text
from labrador.indexer import Indexer
from labrador.search import search
from labrador.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_chunking_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(10))
    chunks = chunk_text(text, 600, 100)
    assert len(chunks) > 3 and all(len(c) <= 700 for c in chunks)


def test_index_search_incremental(tmp_path):
    sample = tmp_path / "sample"
    subprocess.run([sys.executable, str(ROOT / "scripts/make_sample_folder.py"), str(sample)], check=True)
    s = Settings(backend="fake")
    store = Store(tmp_path / "idx")
    ix = Indexer(sample, store, load_embedder(s), s)

    first = ix.run(verbose=False)
    assert first["errors"] == 0 and first["units"] > 10
    assert ix.run(verbose=False)["indexed"] == 0               # nothing changed

    hits = search(store, ix.emb, "upstream connect timeout orders gateway", k=3)
    assert hits and "Screenshot" in hits[0].path                # exact words via OCR + keywords

    (sample / "recipes/banana-bread.txt").unlink()
    assert ix.run(verbose=False)["removed"] == 1
    kinds = store.stats()["units"]
    assert "pdf_page" in kinds and "image" in kinds
