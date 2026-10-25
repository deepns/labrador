"""labrador command line.

  labrador index  ~/Documents/sample      # first pass, then only changed files
  labrador search "dog on a beach" -k 5
  labrador serve                          # web UI on http://127.0.0.1:8765
  labrador watch  ~/Documents/sample      # keep the index fresh while files change
  labrador stats
  labrador eval   evals/sample_queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path

from .config import HOME, Settings, index_dir_for


def _settings(a) -> Settings:
    s = Settings()
    for k in ("backend", "device", "dtype", "dim", "image_tokens", "page_image_tokens"):
        v = getattr(a, k, None)
        if v is not None:
            setattr(s, k, v)
    if getattr(a, "no_ocr", False):
        s.ocr = False
    if getattr(a, "no_page_images", False):
        s.pdf_page_images = False
    return s


def _resolve_index(a) -> Path:
    if getattr(a, "index", None):
        return Path(a.index).expanduser()
    if getattr(a, "folder", None):
        return index_dir_for(Path(a.folder))
    last = HOME / "last_index"
    if last.exists():
        return Path(last.read_text().strip())
    sys.exit("No index yet. Run `labrador index <folder>` first, or pass --index.")


def _open(a):
    from .embedder import load_embedder
    from .store import Store
    idx = _resolve_index(a)
    store = Store(idx)
    s = _settings(a)
    fp = store.get_meta("embedder")
    if fp and fp.startswith("fake"):
        s.backend = "fake"
    if fp and ":" in fp:
        s.dim = int(fp.rsplit(":", 1)[1])
    return store, load_embedder(s), s


def cmd_index(a):
    from .embedder import load_embedder
    from .indexer import Indexer
    from .store import Store
    folder = Path(a.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    idx = Path(a.index).expanduser() if a.index else index_dir_for(folder)
    if a.rebuild and idx.exists():
        shutil.rmtree(idx)
    s = _settings(a)
    print(f"Loading {s.model_id if s.backend == 'gemma' else 'fake embedder'} ...")
    emb = load_embedder(s)
    print(f"  device={getattr(emb, 'device', 'n/a')} dtype={s.dtype} dim={s.dim}")
    from . import ocr
    print(f"  OCR backend: {ocr.backend() if s.ocr else 'off'}")
    store = Store(idx)
    stats = Indexer(folder, store, emb, s).run()
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "last_index").write_text(str(idx))
    print(json.dumps(stats, indent=2))
    print(f"Index: {idx}")


def cmd_search(a):
    from .search import search
    store, emb, _ = _open(a)
    hits = search(store, emb, a.query, k=a.k, only=a.only)
    if a.json:
        print(json.dumps([h.to_dict() for h in hits], indent=2))
        return
    for i, h in enumerate(hits, 1):
        where = f"  p.{h.page}" if h.page else ""
        print(f"{i:>2}. [{h.kind:<13}] {h.path}{where}   cos={h.cosine:.3f}  via {','.join(h.matched)}")
        if h.snippet:
            print(textwrap.indent(textwrap.shorten(h.snippet.replace("\n", " "), 220), "      "))
        if h.media:
            print(f"      picture: {store.media_dir / h.media}")


def cmd_stats(a):
    from .store import Store
    print(json.dumps(Store(_resolve_index(a)).stats(), indent=2))


def cmd_serve(a):
    import uvicorn

    from .web import create_app
    store, emb, s = _open(a)
    print(f"Open http://{a.host}:{a.port}")
    uvicorn.run(create_app(store, emb), host=a.host, port=a.port, log_level="warning")


def cmd_watch(a):
    from .embedder import load_embedder
    from .indexer import Indexer
    from .store import Store
    from .watch import watch
    folder = Path(a.folder).expanduser().resolve()
    s = _settings(a)
    idx = Path(a.index).expanduser() if a.index else index_dir_for(folder)
    ix = Indexer(folder, Store(idx), load_embedder(s), s)
    print(json.dumps(ix.run(), indent=2))
    watch(ix)


def cmd_eval(a):
    from .search import search
    store, emb, _ = _open(a)
    rows = [json.loads(l) for l in Path(a.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.category:
        rows = [r for r in rows if r.get("category") == a.category]

    def ok(r, h):
        # The primary answer must match the page when one is given; "also" answers match by file.
        if r["expect"].lower() in h.path.lower():
            return r.get("page") is None or h.page == r["page"]
        return any(x.lower() in h.path.lower() for x in r.get("also", []))

    results = []
    for r in rows:
        hits = search(store, emb, r["query"], k=10)
        rank = next((i for i, h in enumerate(hits, 1) if ok(r, h)), None)
        results.append({**r, "rank": rank, "top": hits[0].path if hits else None})
        if not a.quiet:
            mark = "✓" if rank == 1 else (f"@{rank}" if rank else "✗")
            top = hits[0].path.split("/")[-1] + (f" p{hits[0].page}" if hits and hits[0].page else "") if hits else "-"
            print(f"{mark:>4}  [{r.get('category', '-')}] {r['query']}  -> {top}")

    def score(rs):
        n = len(rs) or 1
        return (sum(x["rank"] == 1 for x in rs) / n,
                sum(x["rank"] is not None and x["rank"] <= 5 for x in rs) / n,
                sum(1 / x["rank"] for x in rs if x["rank"]) / n)

    cats = sorted({r.get("category", "-") for r in results})
    print(f"\n{'category':<20} {'n':>3}  {'hit@1':>5}  {'hit@5':>5}  {'MRR@10':>6}")
    for c in cats:
        rs = [x for x in results if x.get("category", "-") == c]
        h1, h5, m = score(rs)
        print(f"{c:<20} {len(rs):>3}  {h1:>5.2f}  {h5:>5.2f}  {m:>6.3f}")
    hard = [x for x in results if x.get("hard")]
    if hard:
        h1, h5, m = score(hard)
        print(f"{'(hard negatives)':<20} {len(hard):>3}  {h1:>5.2f}  {h5:>5.2f}  {m:>6.3f}")
    h1, h5, m = score(results)
    print(f"{'ALL':<20} {len(results):>3}  {h1:>5.2f}  {h5:>5.2f}  {m:>6.3f}")
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": {"hit@1": h1, "hit@5": h5, "mrr@10": m, "n": len(results)},
                                           "results": results}, indent=2, ensure_ascii=False))
        print(f"wrote {a.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="labrador", description="Local multimodal search with EmbeddingGemma 2")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, folder=False):
        sp.add_argument("--index", help="index directory (default: ~/.labrador/indexes/<folder>)")
        sp.add_argument("--backend", choices=["gemma", "fake"])
        sp.add_argument("--device", choices=["auto", "mps", "cpu", "cuda"])
        sp.add_argument("--dtype", choices=["float32", "bfloat16"])
        if folder:
            sp.add_argument("folder")
            sp.add_argument("--dim", type=int, choices=[768, 512, 256, 128])
            sp.add_argument("--image-tokens", type=int, choices=[70, 140, 280, 560, 1120])
            sp.add_argument("--page-image-tokens", type=int, choices=[70, 140, 280, 560, 1120])
            sp.add_argument("--no-ocr", action="store_true")
            sp.add_argument("--no-page-images", action="store_true")

    sp = sub.add_parser("index", help="index a folder (incremental)"); common(sp, True)
    sp.add_argument("--rebuild", action="store_true", help="delete the index and start over")
    sp.set_defaults(fn=cmd_index)

    sp = sub.add_parser("search", help="search the index"); common(sp)
    sp.add_argument("query"); sp.add_argument("-k", type=int, default=10)
    sp.add_argument("--only", choices=["text", "image", "pdf", "visual"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("serve", help="web UI"); common(sp)
    sp.add_argument("--host", default="127.0.0.1"); sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("watch", help="index, then re-index files as they change"); common(sp, True)
    sp.set_defaults(fn=cmd_watch)

    sp = sub.add_parser("stats", help="what's in the index"); common(sp)
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("eval", help="hit@k / MRR over a JSONL of {query, expect[, page]}"); common(sp)
    sp.add_argument("file")
    sp.add_argument("--category", help="only queries of this category")
    sp.add_argument("--quiet", action="store_true", help="only the summary table")
    sp.add_argument("--out", help="write per-query results as JSON (to compare configs)")
    sp.set_defaults(fn=cmd_eval)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
