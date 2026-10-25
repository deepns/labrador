"""Deep eval harness for labrador on labrador-bench.

Loads one index + the real embedder once, embeds all queries once, then replays the
search pipeline under switchable settings (ablations) and writes per-query JSON.

    uv run python harness.py INDEX_DIR QUERIES.jsonl OUT.json
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.search import RRF_K, search
from labrador.store import Store

idx, qfile, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = [json.loads(l) for l in qfile.read_text().splitlines() if l.strip()]

store = Store(idx)
fp = store.get_meta("embedder")
s = Settings(dim=int(fp.rsplit(":", 1)[1]))
t = time.time()
emb = load_embedder(s)
load_s = time.time() - t

ids, mods, M = store.matrix()
meta = store.units(ids.tolist())
root = store.get_meta("root").rstrip("/") + "/"

t = time.time()
Q = np.stack([emb.embed_query(r["query"]) for r in rows])
q_ms = (time.time() - t) / len(rows) * 1000
KW = [store.keyword(r["query"]) for r in rows]


def l2(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-12)


def ok(r, path, page):
    rel = path[len(root):] if path.startswith(root) else path
    if r["expect"].lower() in rel.lower():
        return r.get("page") is None or page == r["page"]
    return any(x.lower() in rel.lower() for x in r.get("also", []))


def run(qi, k=10, kw_weight=0.7, dense=True, zscore=True, dim=None, drop_kinds=(), max_per_file=2,
        rrf_k=RRF_K, dense_pool=300, min_n=8):
    """Re-implementation of labrador.search.search with knobs. Returns ranked (path, page, grp, kinds)."""
    keep = np.array([meta[int(u)]["kind"] not in drop_kinds for u in ids])
    I, Mo, Mx = ids[keep], mods[keep], M[keep]
    q = Q[qi]
    if dim:
        Mx, q = l2(Mx[:, :dim]), l2(q[:dim])
    cos = Mx @ q
    if zscore:
        z = np.zeros_like(cos)
        gmu, gsd = cos.mean(), cos.std() + 1e-6
        for m in ("text", "image"):
            mask = Mo == m
            n = int(mask.sum())
            if n == 0:
                continue
            sc = cos[mask]
            mu, sd = (sc.mean(), sc.std() + 1e-6) if n >= min_n else (gmu, gsd)
            z[mask] = (sc - mu) / sd
    else:
        z = cos
    fused = {}
    if dense:
        for rnk, i in enumerate(np.argsort(-z)[:dense_pool]):
            fused[int(I[i])] = 1.0 / (rrf_k + rnk + 1)
    allowed = set(I.tolist())
    if kw_weight:
        for rnk, uid in enumerate(u for u in KW[qi] if u in allowed):
            fused[uid] = fused.get(uid, 0.0) + kw_weight / (rrf_k + rnk + 1)
    groups, per_file = {}, {}
    for uid in sorted(fused, key=fused.get, reverse=True):
        u = meta[uid]
        key = (u["file_id"], u["grp"])
        if key in groups:
            if u["kind"] not in groups[key][3]:
                groups[key][3].append(u["kind"])
            continue
        if per_file.get(u["file_id"], 0) >= max_per_file:
            continue
        per_file[u["file_id"]] = per_file.get(u["file_id"], 0) + 1
        groups[key] = (u["path"], u["page"], u["grp"], [u["kind"]])
        if len(groups) >= k:
            break
    return list(groups.values())


def rank_of(r, hits):
    return next((i for i, h in enumerate(hits, 1) if ok(r, h[0], h[1])), None)


VARIANTS = {
    "baseline": {},
    "dense_only": {"kw_weight": 0},
    "keyword_only": {"dense": False},
    "no_zscore": {"zscore": False},
    "no_zscore_dense_only": {"zscore": False, "kw_weight": 0},
    "kw_0.3": {"kw_weight": 0.3},
    "kw_1.0": {"kw_weight": 1.0},
    "kw_1.5": {"kw_weight": 1.5},
    "rrf_k_10": {"rrf_k": 10},
    "rrf_k_200": {"rrf_k": 200},
    "dim_512": {"dim": 512},
    "dim_256": {"dim": 256},
    "dim_128": {"dim": 128},
    "max_per_file_1": {"max_per_file": 1},
    "max_per_file_5": {"max_per_file": 5},
    "no_ocr_units": {"drop_kinds": ("image_ocr", "pdf_image_ocr", "pdf_ocr")},
    "no_image_vectors": {"drop_kinds": ("image", "pdf_page", "pdf_image")},
    "no_page_images": {"drop_kinds": ("pdf_page",)},
    "text_units_only": {"drop_kinds": ("image", "pdf_page", "pdf_image", "image_ocr", "pdf_image_ocr", "pdf_ocr")},
}

# Sanity: the re-implementation must reproduce labrador.search exactly.
mismatch = 0
t = time.time()
for qi, r in enumerate(rows):
    real = [(h.path, h.page, h.grp) for h in search(store, emb, r["query"], k=10)]
    mine = [h[:3] for h in run(qi)]
    mismatch += real != mine
search_ms = (time.time() - t) / len(rows) * 1000  # includes query embedding

res = {"meta": {"embedder": fp, "units": len(ids), "load_s": load_s, "query_embed_ms": q_ms,
                "search_ms_incl_embed": search_ms, "reimpl_mismatches": mismatch,
                "unit_kinds": store.stats()["units"], "files": store.stats()["files"],
                "errors": [list(e) for e in store.db.execute(
                    "SELECT path, error FROM files WHERE error IS NOT NULL")]},
       "variants": {}}
for name, kw in VARIANTS.items():
    per = []
    for qi, r in enumerate(rows):
        hits = run(qi, **kw)
        per.append({"rank": rank_of(r, hits),
                    "top": [[h[0][len(root):], h[1], h[3]] for h in hits[:5]]})
    res["variants"][name] = per

# Diagnostics for the baseline: where the target's best unit sits in each list.
diag = []
for qi, r in enumerate(rows):
    cos = M @ Q[qi]
    order = np.argsort(-cos)
    tgt = [j for j, u in enumerate(ids) if ok(r, meta[int(u)]["path"], meta[int(u)]["page"])]
    best = {}
    for j in tgt:
        kd = meta[int(ids[j])]["kind"]
        best[kd] = max(best.get(kd, -9), float(cos[j]))
    dense_rank = next((p for p, j in enumerate(order, 1) if j in set(tgt)), None)
    kw_rank = next((p for p, u in enumerate(KW[qi], 1) if int(u) in {int(ids[j]) for j in tgt}), None)
    diag.append({"target_units": len(tgt), "best_cos_by_kind": best, "top_cos": float(cos[order[0]]),
                 "top_kind": meta[int(ids[order[0]])]["kind"], "dense_unit_rank": dense_rank,
                 "kw_unit_rank": kw_rank, "kw_hits": len(KW[qi])})
res["diag"] = diag
res["queries"] = rows
out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
print(json.dumps(res["meta"], indent=1))
