"""labrador command line.

  labrador index  ~/Documents/sample      # first pass, then only changed files
  labrador search "dog on a beach" -k 5
  labrador serve                          # web UI on http://127.0.0.1:8765
  labrador watch  ~/Documents/sample      # keep the index fresh while files change
  labrador ask    "what's my passport number"   # answer from your files with a local LLM (see docs/usage/asking.md)
  labrador stats
  labrador eval   evals/sample_queries.jsonl
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shutil
import sys
import textwrap
import time
from pathlib import Path

from .config import HOME, Settings, index_dir_for
from .trace import Trace


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
    for k, attr in (("llm_url", "llm_url"), ("model", "llm_model"), ("ctx", "context_tokens")):   # ask flags
        if getattr(a, k, None) is not None:
            setattr(s, attr, getattr(a, k))
    if getattr(a, "sources", None) is not None:                        # `ask --k`: sources packed into the prompt
        s.ask_sources, s.ask_search_k = a.sources, max(s.ask_search_k, a.sources)
    if getattr(a, "images", False):
        s.ask_images = 2
    if getattr(a, "llm_extra", None) is not None:
        try:
            extra = json.loads(a.llm_extra)
        except json.JSONDecodeError as e:
            sys.exit(f"--llm-extra is not valid JSON: {e}")
        if not isinstance(extra, dict):
            sys.exit("--llm-extra must be a JSON object, e.g. '{\"think\": false}'")
        s.llm_extra = {**s.llm_extra, **extra}                        # keep defaults such as keep_alive
    if getattr(a, "allow_remote_llm", False):
        s.allow_remote_llm = True
    return s


def _positive_int(v: str) -> int:
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _resolve_index(a) -> Path:
    if getattr(a, "index", None):
        return Path(a.index).expanduser()
    if getattr(a, "folder", None):
        return index_dir_for(Path(a.folder))
    last = HOME / "last_index"
    if last.exists():
        return Path(last.read_text().strip())
    sys.exit("No index yet. Run `labrador index <folder>` first, or pass --index.")


def _open(a, s: Settings | None = None):
    from .embedder import load_embedder
    from .store import Store
    idx = _resolve_index(a)
    store = Store(idx)
    s = s or _settings(a)
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
    t0 = time.perf_counter()
    hits = search(store, emb, a.query, k=a.k, only=a.only)
    sys.stdout.flush()
    print(f"{len(hits)} result{'s' * (len(hits) != 1)} in {time.perf_counter() - t0:.2f} s", file=sys.stderr)
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


def _printable(s: str) -> str:
    """Strip ESC and other C0/C1 control chars (keeps \\n, \\t): model output and paths are untrusted."""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", str(s))


def _status_line(c: dict, masked: bool) -> str:
    if c["refused"]:
        return "refused"
    if c["unverified"]:
        parts = [f"✗ unverified: {', '.join(c['unverified'])}"]
    elif c["citations"] and not c["bad_citations"]:
        cites = ", ".join(f"[{n}]" for n in c["citations"])
        shaky = c["mrz"] == "invalid" or c["confidence"] == "low"
        parts = [f"✗ check the source {cites}" if shaky else f"✓ verified against {cites}"]
    else:
        parts = ["✗ unverified"]
    if c["bad_citations"]:
        parts.append(f"bad citations: {', '.join(c['bad_citations'])}")
    if c["mrz"]:
        parts.append("MRZ check digits " + c["mrz"].replace("invalid", "INVALID"))
    parts.append(f"{c['confidence']} confidence")
    if masked:
        parts.append("--reveal to show")
    return " · ".join(parts)


def _mask_check(c: dict, reveal: bool) -> tuple[dict, bool]:
    """Mask the unverified tokens like the answer body (via answer.mask_text). Returns (check, anything masked)."""
    from .answer import mask_text
    if reveal:
        return c, False
    segs = [mask_text(t) for t in c["unverified"]]
    toks = ["".join(x if isinstance(x, str) else x["mask"] for x in s) for s in segs]
    return {**c, "unverified": toks}, any(not isinstance(x, str) for s in segs for x in s)


def _collect_ask(events, reveal: bool, trace=None) -> int:
    """`ask --json`: print one JSON object (sources, warnings, final answer, check, retried, timings). Returns the exit code."""
    out = {"sources": [], "warnings": [], "answer": "", "check": None, "retried": False}
    for e in events:
        if e["type"] == "sources":
            out["sources"], out["warnings"], out["answer"] = e["sources"], e["warnings"], ""
        elif e["type"] == "delta":
            out["answer"] += e["text"] if "text" in e else (e["raw"] if reveal else e["mask"])
        elif e["type"] == "error":
            print(f"error: {_printable(e['message'])}", file=sys.stderr)
            return 1
        elif e["type"] == "done":
            out["check"], _ = _mask_check(e["check"], reveal)
            out["retried"] = e["retried"]
    if trace:
        out["timings"] = trace.summary()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _render_ask(events, reveal: bool) -> int:
    """Print ask() events: sources, streamed answer, then a status line. Returns the exit code."""
    masked = False
    for e in events:
        if e["type"] == "sources":
            print("Sources")
            for x in e["sources"]:
                page = f" p.{x['page']}" if x["page"] else ""
                date = f", {x['modified']}" if x["modified"] else ""
                pic = ", picture" if x.get("picture") else ""
                print(f"  [{x['n']}] {_printable(x['rel_path'])}{page}  ({_printable(x['kind'])}{date}{pic})")
            for w in e["warnings"]:
                print(f"warning: {_printable(w)}", file=sys.stderr)
            print()
        elif e["type"] == "delta":
            seg = e["text"] if "text" in e else (e["raw"] if reveal else e["mask"])
            masked = masked or "mask" in e and not reveal
            print(_printable(seg), end="", flush=True)
        elif e["type"] == "retry":
            print(f"\n(no answer yet, retrying with \u201c{_printable(e['term'])}\u201d)", flush=True)
            masked = False
        elif e["type"] == "error":
            print(f"\nerror: {_printable(e['message'])}", file=sys.stderr)
            return 1
        elif e["type"] == "done":
            check, m = _mask_check(e["check"], reveal)
            print(f"\n\n{_status_line(check, masked or m)}")
    return 0


def _timings_line(t: dict) -> str:
    """The metrics under the status line, e.g. `retrieval 0.21 s · answer 4.8 s · 38 tok/s`; null metrics are left out."""
    parts = []
    for label, key, scale, fmt in (("retrieval", "retrieval_ms", 1000, "{:.2f} s"), ("answer", "answer_ms", 1000, "{:.1f} s"),
                                   ("first token", "ttft_ms", 1000, "{:.1f} s")):
        if t.get(key) is not None:
            parts.append(f"{label} " + fmt.format(t[key] / scale))
    if t.get("tok_s") is not None:
        parts.append(f"{t['tok_s']:.0f} tok/s")
    if t.get("prompt_tokens") is not None and t.get("completion_tokens") is not None:
        parts.append(f"{t['prompt_tokens']:,.0f} \u2192 {t['completion_tokens']:,.0f} tokens")
    return " \u00b7 ".join(parts)


def _warn_cloud_models(llm) -> None:
    try:
        cloud = any(m.endswith("-cloud") for m in llm.models())
    except Exception:                                  # best effort: a missing or odd /models is not an error
        return
    if cloud:
        print("warning: runtime lists a cloud model; set OLLAMA_NO_CLOUD=1 so nothing leaves the machine",
              file=sys.stderr)


def cmd_ask(a):
    from .answer import ask
    from .llm import LLMError, load_llm
    s = _settings(a)
    try:                                            # validate the LLM flags before loading the embedder
        llm = load_llm(s)
    except LLMError as e:
        sys.exit(f"error: {e}")
    store, emb, s = _open(a, s)
    if hasattr(llm, "models"):
        _warn_cloud_models(llm)
    trace = Trace()
    events = ask(store, emb, llm, a.question, s, a.reveal, a.json, trace=trace)
    if a.json:
        sys.exit(_collect_ask(events, a.reveal, trace))
    code = _render_ask(events, a.reveal)
    if code == 0:                                   # the generator has finished, so the trace is complete
        sm = trace.summary()
        sys.stdout.flush()                          # keep the stderr lines off the end of the answer when piped
        if line := _timings_line(sm):
            print(line, file=sys.stderr)
        if sm["cut_off"]:
            print(f"the answer was cut off at llm_max_tokens ({s.llm_max_tokens})", file=sys.stderr)
    sys.exit(code)


def cmd_stats(a):
    from .store import Store
    print(json.dumps(Store(_resolve_index(a)).stats(), indent=2))


def _is_loopback(host: str) -> bool:
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _serve_hosts(a) -> set[str]:
    """Host headers the web UI accepts; refuses a non-loopback --host unless --allow-lan."""
    hosts = {"127.0.0.1", "localhost"}
    if _is_loopback(a.host):
        return hosts | {a.host}   # browsers send the literal host, e.g. ::1 or 127.0.0.2
    if not a.allow_lan:
        sys.exit(f"Refusing to serve on {a.host}: the index holds private text. Pass --allow-lan to expose it.")
    print(f"WARNING: serving your private index to the network on {a.host}; anyone who can reach it can read it.")
    if a.host in ("0.0.0.0", "::"):
        print("  Wildcard host: DNS-rebinding protection (Host check) is off.")
        return {"*"}
    return hosts | {a.host}


def cmd_serve(a):
    allowed = _serve_hosts(a)
    import uvicorn

    from .llm import LLMError, load_llm
    from .web import create_app
    s = _settings(a)
    try:                                            # validate the LLM flags before loading the embedder
        llm = load_llm(s)
    except LLMError as e:
        sys.exit(f"error: {e}")
    store, emb, s = _open(a, s)
    if hasattr(llm, "models"):
        _warn_cloud_models(llm)
    print(f"Open http://{a.host}:{a.port}")
    uvicorn.run(create_app(store, emb, allowed, llm, s), host=a.host, port=a.port, log_level="warning")


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


def _qa_match(pattern: str, text: str) -> bool:
    """"re:<regex>" searches; anything else is a case-insensitive substring."""
    return bool(re.search(pattern[3:], text)) if pattern.startswith("re:") else pattern.lower() in text.lower()


def _qa_row(r, sources, text, check, retried, secs) -> dict:
    ans, refused = r.get("answerable", True), check["refused"]
    expect = r["expect"] if isinstance(r["expect"], list) else [r["expect"]]
    cited = [sources[n - 1] for n in check["citations"] if 0 < n <= len(sources)]
    bad = not refused and any(_qa_match(b, text) for b in r.get("bad", []))
    return {**r, "refused": refused, "em": ans and not refused and _qa_match(r["answer"], text),
            "cite_hit": ans and any(c in expect for c in cited),
            "cite_prec": sum(c in expect for c in cited) / len(cited) if ans and cited else None,
            "false_answer": (not ans and not refused) or bad, "false_refusal": ans and refused,
            "unverified": bool(check["unverified"]), "hit5": ans and any(x in expect for x in sources),
            "confidence": check["confidence"], "retried": retried, "seconds": secs,
            "answer_text": text, "sources": sources, "cited": cited}


def _qa_rates(rs) -> dict:
    """Each rate is over the rows where it applies (None when none do)."""
    def rate(key, rows):
        return sum(bool(x[key]) for x in rows) / len(rows) if rows else None
    a = [x for x in rs if x.get("answerable", True)]
    cp = [x["cite_prec"] for x in rs if x["cite_prec"] is not None]
    return {"n": len(rs), "em": rate("em", a), "cite_hit": rate("cite_hit", a),
            "cite_prec": sum(cp) / len(cp) if cp else None, "false_ans": rate("false_answer", rs),
            "false_ref": rate("false_refusal", a), "unverif": rate("unverified", rs),
            "hit@5": rate("hit5", a), "errors": sum(bool(x["error"]) for x in rs), "sec/q": sum(x["seconds"] for x in rs) / len(rs) if rs else None}


def cmd_eval_answers(a):
    from .answer import ask
    from .llm import LLMError, load_llm
    s = _settings(a)
    try:
        llm = load_llm(s)
    except LLMError as e:
        sys.exit(f"error: {e}")
    store, emb, s = _open(a, s)
    rows = [json.loads(l) for l in Path(a.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.category:
        rows = [r for r in rows if r.get("category") == a.category]
    results = []
    for r in rows:
        t0, sources, text, check, retried, err = time.perf_counter(), [], "", {}, False, None
        # Score the streamed text path (json_mode=False): Ollama's MLX runner returns 501 for structured output.
        for ev in ask(store, emb, llm, r["question"], s, reveal=True):
            if ev["type"] == "error":
                err, check = ev["message"], {"refused": True, "citations": [], "unverified": [], "confidence": "error"}
                break
            if ev["type"] == "sources":
                sources, text = [x["rel_path"] for x in ev["sources"]], ""    # a retry restarts the answer
            elif ev["type"] == "delta":
                text += ev.get("text") or ev.get("raw") or ""
            elif ev["type"] == "done":
                check, retried = ev["check"], ev["retried"]
        res = {**_qa_row(r, sources, text, check, retried, time.perf_counter() - t0), "error": err}
        results.append(res)
        if not a.quiet:
            good = (res["em"] if r.get("answerable", True) else True) and not res["false_answer"]
            print(f"{'✓' if good else '✗':>4}  [{r.get('category', '-')}] {r['question']}  -> "
                  f"{_printable(err or ' '.join(text.split()))[:80]}")
    f = lambda v: "-" if v is None else f"{v:.2f}"
    cols = ["em", "cite_hit", "cite_prec", "false_ans", "false_ref", "unverif", "hit@5"]
    print(f"\n{'category':<20} {'n':>3}  " + "  ".join(f"{c:>9}" for c in cols) + "  sec/q")
    by_cat = {c: _qa_rates([x for x in results if x.get("category", "-") == c])
              for c in sorted({x.get("category", "-") for x in results})}
    summary = _qa_rates(results)
    for c, m in {**by_cat, "ALL": summary}.items():
        print(f"{c:<20} {m['n']:>3}  " + "  ".join(f"{f(m[k]):>9}" for k in cols) + f"  {m['sec/q'] or 0:>5.1f}")
    if a.out:
        cfg = {"model": s.llm_model, "llm_url": s.llm_url, "llm_extra": s.llm_extra, "temperature": s.temperature,
               "context_tokens": s.context_tokens, "ask_sources": s.ask_sources, "ask_search_k": s.ask_search_k,
               "ask_images": s.ask_images,
               "embedder": store.get_meta("embedder")}
        Path(a.out).write_text(json.dumps({"config": cfg, "summary": summary, "by_category": by_cat,
                                           "results": results}, indent=2, ensure_ascii=False))
        print(f"wrote {a.out}")
    if summary["errors"]:
        sys.exit(f"{summary['errors']} questions failed with an LLM error")


def cmd_eval(a):
    if a.answers:
        return cmd_eval_answers(a)
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


def build_parser() -> argparse.ArgumentParser:
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

    def llm_flags(sp):
        sp.add_argument("--model", help="LLM name as the runtime knows it (default: qwen3.5:4b)")
        sp.add_argument("--llm-url", help="OpenAI-compatible base URL (default: local Ollama; `fake` for a canned answer)")
        sp.add_argument("--llm-extra", help="JSON object passed to the runtime, merged over the default keep_alive")
        sp.add_argument("--ctx", type=_positive_int, help="prompt budget in tokens; match OLLAMA_CONTEXT_LENGTH")
        sp.add_argument("--allow-remote-llm", action="store_true", help="skip the loopback check (sends files off-machine)")

    sp = sub.add_parser("ask", help="answer a question from your files with a local LLM"); common(sp)
    sp.add_argument("question")
    sp.add_argument("--reveal", action="store_true", help="show IDs and numbers unmasked")
    sp.add_argument("--json", action="store_true", help="ask the model for a structured reply and print one JSON object (not streamed)")
    sp.add_argument("-k", "--k", dest="sources", type=_positive_int, help="sources to give the model (default: 5)")
    llm_flags(sp)
    sp.add_argument("--images", action="store_true", help="attach the original picture of the top image/PDF-page sources (needs a vision model)")
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("serve", help="web UI"); common(sp)
    sp.add_argument("--host", default="127.0.0.1"); sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--allow-lan", action="store_true", help="allow a non-loopback --host (exposes the index)")
    llm_flags(sp)
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("watch", help="index, then re-index files as they change"); common(sp, True)
    sp.set_defaults(fn=cmd_watch)

    sp = sub.add_parser("stats", help="what's in the index"); common(sp)
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("eval", help="hit@k / MRR over {query, expect[, page]} rows; with --answers, score `ask` over qa.jsonl"); common(sp)
    sp.add_argument("file")
    sp.add_argument("--answers", action="store_true", help="score `ask` answers over a qa.jsonl instead of search ranking")
    sp.add_argument("-k", "--k", dest="sources", type=_positive_int, help="with --answers: sources to give the model (default: 5)")
    llm_flags(sp)
    sp.add_argument("--images", action="store_true", help="attach the original picture of the top image/PDF-page sources (needs a vision model)")
    sp.add_argument("--category", help="only queries of this category")
    sp.add_argument("--quiet", action="store_true", help="only the summary table")
    sp.add_argument("--out", help="write per-query results as JSON (to compare configs)")
    sp.set_defaults(fn=cmd_eval)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
