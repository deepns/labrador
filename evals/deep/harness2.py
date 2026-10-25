"""Round 2: keyword-branch fixes, ablations on the better base, 2-fold cross-validated selection.

    uv run python harness2.py INDEX_DIR QUERIES.jsonl OUT.json
"""
import itertools
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

from labrador.config import Settings
from labrador.embedder import load_embedder
from labrador.store import Store

idx, qfile, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = [json.loads(l) for l in qfile.read_text().splitlines() if l.strip()]
store = Store(idx)
emb = load_embedder(Settings(dim=int(store.get_meta("embedder").rsplit(":", 1)[1])))
ids, mods, M = store.matrix()
meta = store.units(ids.tolist())
root = store.get_meta("root").rstrip("/") + "/"
Q = np.stack([emb.embed_query(r["query"]) for r in rows])
N = len(rows)

STOP = set("""a an and are as at be but by can could did do does for from had has have how i if in into is it
its me my of on or our so that the their them then there these they this to too was we were what when where
which while who whom why will with would you your about after all also any been before being both each few
more most other over same should some such than through under until up very off out own just now only""".split())


def kw_query(q, stop=False, phrase=False):
    parts = []
    for tok in q.split():
        words = [w for w in re.findall(r"\w+", tok.lower()) if len(w) > 1]   # same filter as Store.keyword
        if stop:
            words = [w for w in words if w not in STOP]
        if not words:
            continue
        if phrase and len(words) > 1:            # keep '58-QX-2210' / '45,210' together
            parts.append('"' + " ".join(words) + '"')
        else:
            parts.extend(f'"{w}"' for w in words)
    return parts


def keyword(q, stop=False, phrase=False, mode="or", limit=200):
    parts = kw_query(q, stop, phrase)
    if not parts:
        return []
    sql = "SELECT rowid FROM units_fts WHERE units_fts MATCH ? ORDER BY bm25(units_fts, 1.0, 0.5) LIMIT ?"
    try:
        if mode == "and_or":                      # all terms first, then the OR tail
            first = [r[0] for r in store.db.execute(sql, (" AND ".join(parts), limit))]
            rest = [r[0] for r in store.db.execute(sql, (" OR ".join(parts), limit)) if r[0] not in set(first)]
            return (first + rest)[:limit]
        if mode == "and":
            return [r[0] for r in store.db.execute(sql, (" AND ".join(parts), limit))]
        return [r[0] for r in store.db.execute(sql, (" OR ".join(parts), limit))]
    except sqlite3.OperationalError:
        return []


def l2(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-12)


def ok(r, path, page):
    rel = path[len(root):] if path.startswith(root) else path
    if r["expect"].lower() in rel.lower():
        return r.get("page") is None or page == r["page"]
    return any(x.lower() in rel.lower() for x in r.get("also", []))


KCACHE = {}


def run(qi, kw_weight=0.7, rrf_k=60, zscore=True, dim=None, drop_kinds=(), stop=False, phrase=False,
        mode="or", kw_top=200, dense=True, k=10):
    keep = np.array([meta[int(u)]["kind"] not in drop_kinds for u in ids])
    I, Mo, Mx = ids[keep], mods[keep], M[keep]
    q = Q[qi]
    if dim:
        Mx, q = l2(Mx[:, :dim]), l2(q[:dim])
    cos = Mx @ q
    z = cos.copy()
    if zscore:
        for m in ("text", "image"):
            mask = Mo == m
            if mask.sum() >= 8:
                z[mask] = (cos[mask] - cos[mask].mean()) / (cos[mask].std() + 1e-6)
    fused = {}
    if dense:
        for rnk, i in enumerate(np.argsort(-z)[:300]):
            fused[int(I[i])] = 1.0 / (rrf_k + rnk + 1)
    if kw_weight:
        key = (qi, stop, phrase, mode)
        if key not in KCACHE:
            KCACHE[key] = keyword(rows[qi]["query"], stop, phrase, mode)
        allowed = set(I.tolist())
        for rnk, uid in enumerate([u for u in KCACHE[key] if u in allowed][:kw_top]):
            fused[uid] = fused.get(uid, 0.0) + kw_weight / (rrf_k + rnk + 1)
    groups, per_file = {}, {}
    for uid in sorted(fused, key=fused.get, reverse=True):
        u = meta[uid]
        g = (u["file_id"], u["grp"])
        if g in groups:
            continue
        if per_file.get(u["file_id"], 0) >= 2:
            continue
        per_file[u["file_id"]] = per_file.get(u["file_id"], 0) + 1
        groups[g] = (u["path"], u["page"])
        if len(groups) >= k:
            break
    return next((i for i, h in enumerate(groups.values(), 1) if ok(rows[qi], *h)), None)


def evaluate(cfg, idxs=None):
    return [run(qi, **cfg) for qi in (idxs if idxs is not None else range(N))]


def mrr(rs):
    return sum(1 / r for r in rs if r) / len(rs)


BASE = {}
DENSE = {"kw_weight": 0}
FIX = {"stop": True, "phrase": True}
named = {
    "baseline": BASE,
    "dense_only": DENSE,
    "stop": {"stop": True},
    "phrase": {"phrase": True},
    "stop+phrase": FIX,
    "stop+phrase_top10": {**FIX, "kw_top": 10},
    "stop+phrase_top20": {**FIX, "kw_top": 20},
    "stop+phrase_and_or": {**FIX, "mode": "and_or"},
    "stop+phrase_and": {**FIX, "mode": "and"},
    "stop+phrase_and_w0.7": {**FIX, "mode": "and"},
    "stop+phrase_and_w1.0": {**FIX, "mode": "and", "kw_weight": 1.0},
    "stop+phrase_and_top10": {**FIX, "mode": "and", "kw_top": 10},
    "stop+phrase_top10_w0.3": {**FIX, "kw_top": 10, "kw_weight": 0.3},
    "top10": {"kw_top": 10},
    "top5": {"kw_top": 5},
    "and": {"mode": "and"},
}
# Ablations on the dense-only base (no keyword noise masking the effect)
for nm, dk in {"no_ocr": ("image_ocr", "pdf_image_ocr", "pdf_ocr"),
               "no_image_vec": ("image", "pdf_page", "pdf_image"),
               "no_page_img": ("pdf_page",), "no_embedded_img": ("pdf_image", "pdf_image_ocr")}.items():
    named[f"dense_{nm}"] = {**DENSE, "drop_kinds": dk}
for d in (512, 256, 128):
    named[f"dense_dim{d}"] = {**DENSE, "dim": d}
named["dense_no_zscore"] = {**DENSE, "zscore": False}

results = {n: evaluate(c) for n, c in named.items()}

# Grid for cross-validated selection
grid = []
for stop, phrase, mode, kw_top, w, rk in itertools.product(
        [False, True], [False, True], ["or", "and", "and_or"], [200, 20, 10, 5], [0.0, 0.3, 0.7, 1.0],
        [10, 60]):
    if w == 0 and (stop or phrase or mode != "or" or kw_top != 200):
        continue
    grid.append({"stop": stop, "phrase": phrase, "mode": mode, "kw_top": kw_top, "kw_weight": w, "rrf_k": rk})
grid_ranks = [evaluate(c) for c in grid]

random.seed(1)
cv = []
for rep in range(20):                     # 20 random 50/50 splits, stratified by category
    by_cat = {}
    for i, r in enumerate(rows):
        by_cat.setdefault(r.get("category", "-"), []).append(i)
    A = []
    for c, ix in by_cat.items():
        ix = ix[:]
        random.shuffle(ix)
        A += ix[: len(ix) // 2 + (rep % 2 if len(ix) % 2 else 0)]
    B = [i for i in range(N) if i not in set(A)]
    for tr, te in ((A, B), (B, A)):
        best = max(range(len(grid)), key=lambda g: mrr([grid_ranks[g][i] for i in tr]))
        cv.append({"cfg": grid[best], "test_mrr": mrr([grid_ranks[best][i] for i in te]),
                   "test_base": mrr([results["baseline"][i] for i in te]),
                   "test_dense": mrr([results["dense_only"][i] for i in te])})

top_grid = sorted(range(len(grid)), key=lambda g: -mrr(grid_ranks[g]))[:15]
out.write_text(json.dumps({"named": results, "grid": grid, "grid_ranks": grid_ranks, "cv": cv,
                           "top_grid": top_grid, "queries": rows}, ensure_ascii=False))

cats = sorted({r.get("category", "-") for r in rows})
hard = [i for i, r in enumerate(rows) if r.get("hard")]
print(f"{'variant':<26}{'h@1':>6}{'h@5':>6}{'MRR':>7}{'exact':>7}{'hard':>7}")
for n, rs in results.items():
    ex = [rs[i] for i, r in enumerate(rows) if r.get("category", "-") == "text-exact"]
    print(f"{n:<26}{sum(r == 1 for r in rs)/N:>6.2f}{sum(bool(r) and r <= 5 for r in rs)/N:>6.2f}"
          f"{mrr(rs):>7.3f}{mrr(ex):>7.3f}{mrr([rs[i] for i in hard]):>7.3f}")
print("\nTop grid configs (full set, optimistic):")
for g in top_grid:
    rs = grid_ranks[g]
    ex = [rs[i] for i, r in enumerate(rows) if r.get("category", "-") == "text-exact"]
    print(f"  MRR {mrr(rs):.3f} exact {mrr(ex):.3f} h@1 {sum(r == 1 for r in rs)/N:.2f}  {grid[g]}")
import statistics as st

print(f"\nCV (40 folds): selected-config test MRR {st.mean(c['test_mrr'] for c in cv):.3f} "
      f"(sd {st.stdev(c['test_mrr'] for c in cv):.3f}); baseline {st.mean(c['test_base'] for c in cv):.3f}; "
      f"dense_only {st.mean(c['test_dense'] for c in cv):.3f}")
from collections import Counter

print("Selected configs:", Counter(json.dumps(c["cfg"], sort_keys=True) for c in cv).most_common(5))
print("\nPer-category MRR")
show = ["baseline", "dense_only", "stop+phrase", "stop+phrase_and", "stop+phrase_top10"]
print(f"{'':<20}" + "".join(f"{s[:16]:>18}" for s in show))
for c in cats:
    ix = [i for i, r in enumerate(rows) if r.get("category", "-") == c]
    print(f"{c:<20}" + "".join(f"{mrr([results[s][i] for i in ix]):>18.3f}" for s in show))
