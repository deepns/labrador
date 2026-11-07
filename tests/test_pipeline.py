"""End-to-end plumbing test with the fake embedder (no model download).

    uv run --extra dev pytest -q
"""

import subprocess
import sys
from pathlib import Path

import pytest

from labrador import ocr
from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.extractors import chunk_text
from labrador.indexer import Indexer
from labrador.search import keywords, search
from labrador.store import Store

ROOT = Path(__file__).resolve().parents[1]


def test_chunking_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(10))
    chunks = chunk_text(text, 600, 100)
    assert len(chunks) > 3 and all(len(c) <= 700 for c in chunks)


def _index_sample(tmp_path):
    sample = tmp_path / "sample"
    subprocess.run([sys.executable, str(ROOT / "scripts/make_sample_folder.py"), str(sample)], check=True)
    s = Settings(backend="fake")
    store = Store(tmp_path / "idx")
    ix = Indexer(sample, store, load_embedder(s), s)
    return sample, store, ix


def test_index_search_incremental(tmp_path):
    sample, store, ix = _index_sample(tmp_path)

    first = ix.run(verbose=False)
    assert first["errors"] == 0 and first["units"] > 10
    assert ix.run(verbose=False)["indexed"] == 0               # nothing changed

    (sample / "recipes/banana-bread.txt").unlink()
    assert ix.run(verbose=False)["removed"] == 1
    kinds = store.stats()["units"]
    assert "pdf_page" in kinds and "image" in kinds


def test_question_keywords_match(tmp_path):
    _, store, ix = _index_sample(tmp_path)
    ix.run(verbose=False)
    q = "what's in my banana bread?"
    assert keywords(q) == "banana bread"
    assert store.keyword(q) == []                              # "what", "my" are in no unit
    hit = store.units(store.keyword(keywords(q))[:1])
    assert "banana-bread" in next(iter(hit.values()))["path"]


# The screenshot's words exist only as OCR text: without a backend the fake embedder's
# random vectors decide the ranking, so this checks nothing and is skipped instead.
@pytest.mark.skipif(ocr.backend() == "none", reason="no OCR backend (install the mac or tesseract extra)")
def test_ocr_keywords_find_screenshot(tmp_path):
    _, store, ix = _index_sample(tmp_path)
    ix.run(verbose=False)
    hits = search(store, ix.emb, "upstream connect timeout orders gateway", k=3)
    assert hits and "Screenshot" in hits[0].path                # exact words via OCR + keywords
