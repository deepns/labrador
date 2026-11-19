"""Time `ask` over a QA file, one trace per question, and compare runs.

    uv run python scripts/ask_bench.py run bench/data/qa.jsonl --index ~/.labrador/indexes/<folder>-<hash> --tag gemma4
    uv run python scripts/ask_bench.py summary evals/out/ask-bench

`run` loads the embedder once (like `labrador serve`), times its load and first embed, then asks every question with a
`Trace`, scores it with the same `_qa_row` as `eval --answers` and writes `<out>/<tag>.json`: the config, the load
times, and per question its row, `timings` and span `tree`. Takes the LLM flags of `ask` (`--model`, `--llm-url`,
`--ctx`, `-k`) plus `--extra` (JSON merged over `llm_extra`), `--limit N` and `--out DIR`. `summary` prints one table row per run JSON (quality
rates, p50/p95 of the stages, p50 of the runtime numbers) and a wall-time share per stage. Outputs go in `evals/out/`.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from labrador.cli import _open, _positive_int, _qa_rates, _qa_row, _settings
from labrador.trace import Trace


def spans(node, name):
    return ([node] if node["name"] == name else []) + [x for c in node["children"] for x in spans(c, name)]


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))] if xs else None


def run(a):
    from labrador.answer import ask
    from labrador.llm import LLMError, load_llm
    s = _settings(a)
    try:
        llm = load_llm(s)
    except LLMError as e:
        sys.exit(f"error: {e}")
    t = time.perf_counter()
    store, emb, s = _open(a, s)                                # embedder loaded once; dim/backend from the index meta
    load_s = time.perf_counter() - t
    t = time.perf_counter()
    emb.embed_query("warm up")
    first_s = time.perf_counter() - t
    print(f"[{a.tag}] model={s.llm_model} extra={s.llm_extra} embedder load {load_s:.1f}s, first embed {first_s:.2f}s")
    rows = [json.loads(l) for l in Path(a.qa).read_text(encoding="utf-8").splitlines() if l.strip()][: a.limit]
    results = []
    for i, r in enumerate(rows):
        tr, t0, sources, text, check, retried, err = Trace(), time.perf_counter(), [], "", {}, False, None
        for ev in ask(store, emb, llm, r["question"], s, reveal=True, trace=tr):
            if ev["type"] == "error":
                err, check = ev["message"], {"refused": True, "citations": [], "unverified": [], "confidence": "error"}
                break
            if ev["type"] == "sources":
                sources, text = [x["rel_path"] for x in ev["sources"]], ""
            elif ev["type"] == "delta":
                text += ev.get("text") or ev.get("raw") or ""
            elif ev["type"] == "done":
                check, retried = ev["check"], ev["retried"]
        row = {**_qa_row(r, sources, text, check, retried, time.perf_counter() - t0), "error": err,
               "timings": tr.summary(), "tree": tr.tree()}
        results.append(row)
        tm = row["timings"]
        print(f"{i:>2} {'ok ' if row['em'] else 'x  '} total {tm['total_ms'] / 1000:6.1f}s retr {tm['retrieval_ms']:7.0f}ms "
              f"ttft {(tm['ttft_ms'] or 0) / 1000:5.1f}s tok/s {tm['tok_s']} {tm['prompt_tokens']}->{tm['completion_tokens']} "
              f"att {tm['attempts']} cut {tm['cut_off']} | {r['question'][:50]}", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = {"model": s.llm_model, "llm_url": s.llm_url, "llm_extra": s.llm_extra, "context_tokens": s.context_tokens,
           "ask_sources": s.ask_sources, "embedder": store.get_meta("embedder")}
    (out / f"{a.tag}.json").write_text(json.dumps(
        {"tag": a.tag, "config": cfg, "embedder_load_s": load_s, "first_embed_s": first_s, "results": results},
        indent=1, ensure_ascii=False))
    print(f"wrote {out / (a.tag + '.json')}")


def metrics(results):
    """Per-question lists, in the units the table prints (s, or ms for retrieval and embed)."""
    m = {k: [] for k in ("total", "retrieval", "embed", "prefill", "think", "decode", "ttft", "ctoks",
                         "prefill_tps", "decode_tps", "tok_ratio")}
    for r in results:
        t, tree = r["timings"], r["tree"]
        gens = spans(tree, "generate")
        g, ms = (gens[-1]["attrs"], gens[-1]["ms"]) if gens else ({}, 0)
        ttft, packs = g.get("ttft_ms"), spans(tree, "pack")
        est = packs[-1]["attrs"].get("est_tokens") if packs else None
        m["total"].append(t["total_ms"] / 1000)
        m["retrieval"].append(t["retrieval_ms"])
        m["embed"].append(sum(x["ms"] for x in spans(tree, "embed_query")))
        m["prefill"].append(g["headers_ms"] / 1000 if g.get("headers_ms") is not None else None)   # load + queue + prefill
        m["ttft"].append(ttft / 1000 if ttft else None)
        m["think"].append((ttft - g["first_chunk_ms"]) / 1000 if ttft and g.get("first_chunk_ms") is not None else None)
        m["decode"].append((ms - ttft) / 1000 if ttft else None)
        m["ctoks"].append(g.get("completion_tokens"))
        m["prefill_tps"].append(g.get("rt_prompt_per_second"))
        m["decode_tps"].append(g.get("rt_predicted_per_second"))
        m["tok_ratio"].append(g["prompt_tokens"] / est if g.get("prompt_tokens") and est else None)
    return m


def summary(a):
    runs = [json.loads(f.read_text()) for f in sorted(Path(a.dir).glob("*.json"))]
    if not runs:
        sys.exit(f"no run JSON files in {a.dir}")
    f = lambda v, w, p=1: f"{'-' if v is None else format(v, f'.{p}f'):>{w}}"
    cols = [("total", 1), ("retrieval", 0), ("embed", 0)]
    print(f"{'run':<14}{'n':>3}  " + " ".join(f"{c:>6}" for c in ("em", "cite", "prec", "false"))
          + " | " + " ".join(f"{c + ' p50/p95':>16}" for c, _ in cols) + " | "
          + " ".join(f"{c:>8}" for c in ("prefill", "think", "decode", "ttft", "ctoks", "pf t/s", "dc t/s", "tok/est")))
    for d in runs:
        m, q = metrics(d["results"]), _qa_rates(d["results"])
        quality = " ".join(f(q[k], 6, 2) for k in ("em", "cite_hit", "cite_prec", "false_ans"))
        stages = " ".join(f"{f(pct(m[k], .5), 7, p)}/{f(pct(m[k], .95), 8, p)}" for k, p in cols)
        mid = " ".join(f(pct(m[k], .5), 8, p) for k, p in (("prefill", 2), ("think", 1), ("decode", 1), ("ttft", 1),
                                                           ("ctoks", 0), ("prefill_tps", 0), ("decode_tps", 1), ("tok_ratio", 2)))
        print(f"{d['tag']:<14}{q['n']:>3}  {quality} | {stages} | {mid}")
    print("\nshare of wall time (prefill = load + queue + prefill):")
    for d in runs:
        m = metrics(d["results"])
        tot = sum(m["total"]) or 1
        share = {"retrieval": sum(m["retrieval"]) / 1000, **{k: sum(x for x in m[k] if x) for k in ("prefill", "think", "decode")}}
        print(f"  {d['tag']:<14}" + ", ".join(f"{k} {v / tot:.0%}" for k, v in share.items())
              + f" | embedder load {d['embedder_load_s']:.1f}s, first embed {d['first_embed_s']:.2f}s")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="ask every question in a QA file, with traces")
    r.add_argument("qa", help="QA file (JSONL), e.g. bench/data/qa.jsonl")
    r.add_argument("--index", required=True, help="index directory")
    r.add_argument("--tag", required=True, help="run name; the output is <out>/<tag>.json")
    r.add_argument("--model")
    r.add_argument("--llm-url", dest="llm_url")
    r.add_argument("--extra", dest="llm_extra", help="JSON merged over llm_extra")
    r.add_argument("--ctx", type=_positive_int)
    r.add_argument("-k", dest="sources", type=_positive_int, help="sources packed into the prompt")
    r.add_argument("--limit", type=int, help="only the first N questions")
    r.add_argument("--out", default="evals/out/ask-bench")
    r.set_defaults(fn=run)
    s = sub.add_parser("summary", help="one table row per run JSON in DIR")
    s.add_argument("dir")
    s.set_defaults(fn=summary)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
