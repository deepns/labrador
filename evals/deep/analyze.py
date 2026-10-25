"""Summaries from harness.py output: per-category, hard negatives, paired bootstrap, failures.

    python3 analyze.py results.json
"""
import json
import random
import sys
from collections import defaultdict

R = json.load(open(sys.argv[1]))
Q = R["queries"]
V = R["variants"]
N = len(Q)


def metrics(ranks):
    n = len(ranks) or 1
    return (sum(r == 1 for r in ranks) / n, sum(r is not None and r <= 5 for r in ranks) / n,
            sum(1 / r for r in ranks if r) / n)


def ranks(name, idx=None):
    return [V[name][i]["rank"] for i in (idx if idx is not None else range(N))]


def rr(r):
    return 1 / r if r else 0.0


print("META", json.dumps({k: v for k, v in R["meta"].items() if k != "errors"}, indent=1))
print("ERRORS", R["meta"]["errors"])

# Bootstrap CI for baseline
random.seed(0)
B = 5000
base_rr = [rr(r) for r in ranks("baseline")]
base_h1 = [r == 1 for r in ranks("baseline")]
boots_m, boots_h = [], []
for _ in range(B):
    s = [random.randrange(N) for _ in range(N)]
    boots_m.append(sum(base_rr[i] for i in s) / N)
    boots_h.append(sum(base_h1[i] for i in s) / N)
boots_m.sort(); boots_h.sort()
h1, h5, m = metrics(ranks("baseline"))
print(f"\nBASELINE hit@1 {h1:.3f} [{boots_h[125]:.3f},{boots_h[4875]:.3f}]  hit@5 {h5:.3f}  "
      f"MRR {m:.3f} [{boots_m[125]:.3f},{boots_m[4875]:.3f}]")

cats = defaultdict(list)
for i, q in enumerate(Q):
    cats[q["category"]].append(i)
hard = [i for i, q in enumerate(Q) if q.get("hard")]

print(f"\n{'category':<20}{'n':>4}{'hit@1':>7}{'hit@5':>7}{'MRR':>7}   miss@10")
for c in sorted(cats, key=lambda c: metrics(ranks('baseline', cats[c]))[2]):
    idx = cats[c]
    a, b, mm = metrics(ranks("baseline", idx))
    miss = sum(r is None for r in ranks("baseline", idx))
    print(f"{c:<20}{len(idx):>4}{a:>7.2f}{b:>7.2f}{mm:>7.3f}   {miss}")
a, b, mm = metrics(ranks("baseline", hard))
print(f"{'(hard)':<20}{len(hard):>4}{a:>7.2f}{b:>7.2f}{mm:>7.3f}")
nh = [i for i in range(N) if i not in hard]
a, b, mm = metrics(ranks("baseline", nh))
print(f"{'(not hard)':<20}{len(nh):>4}{a:>7.2f}{b:>7.2f}{mm:>7.3f}")

# Variants: paired bootstrap on MRR difference vs baseline
print(f"\n{'variant':<24}{'hit@1':>7}{'hit@5':>7}{'MRR':>7}{'dMRR':>8}  95% CI          wins/losses(rank)")
for name in V:
    vr = [rr(r) for r in ranks(name)]
    d = [vr[i] - base_rr[i] for i in range(N)]
    bs = sorted(sum(d[random.randrange(N)] for _ in range(N)) / N for _ in range(2000))
    a, b, mm = metrics(ranks(name))
    w = sum(x > 1e-9 for x in d); l = sum(x < -1e-9 for x in d)
    flag = "*" if bs[50] > 0 or bs[1950] < 0 else " "
    print(f"{name:<24}{a:>7.2f}{b:>7.2f}{mm:>7.3f}{sum(d)/N:>+8.3f}  [{bs[50]:+.3f},{bs[1950]:+.3f}]{flag} {w}/{l}")

# Per-category MRR for key variants
keys = ["baseline", "dense_only", "keyword_only", "no_zscore", "no_ocr_units", "no_image_vectors",
        "text_units_only", "dim_256", "kw_1.5"]
print("\nPer-category MRR")
print(f"{'category':<20}" + "".join(f"{k[:11]:>12}" for k in keys))
for c in sorted(cats):
    print(f"{c:<20}" + "".join(f"{metrics(ranks(k, cats[c]))[2]:>12.3f}" for k in keys))
print(f"{'(hard)':<20}" + "".join(f"{metrics(ranks(k, hard))[2]:>12.3f}" for k in keys))

# Failures (rank != 1) in baseline
print("\nNON-TOP-1 QUERIES (baseline)")
for i, q in enumerate(Q):
    r = V["baseline"][i]["rank"]
    if r == 1:
        continue
    dg = R["diag"][i]
    print(f"\n[{q['category']}{' HARD' if q.get('hard') else ''}] rank={r}  {q['query']!r}")
    print(f"   expect: {q['expect']}{' p'+str(q['page']) if q.get('page') else ''}"
          f"{'  also='+str(q['also']) if q.get('also') else ''}{'  note: '+q['note'] if q.get('note') else ''}")
    print(f"   target units={dg['target_units']} dense_unit_rank={dg['dense_unit_rank']} "
          f"kw_unit_rank={dg['kw_unit_rank']} (kw hits {dg['kw_hits']})  "
          f"best_cos={ {k: round(v, 3) for k, v in dg['best_cos_by_kind'].items()} }  "
          f"top_cos={dg['top_cos']:.3f} ({dg['top_kind']})")
    for t in V["baseline"][i]["top"][:3]:
        print(f"     -> {t[0]}{' p'+str(t[1]) if t[1] else ''}  {t[2]}")
    alt = {n: V[n][i]["rank"] for n in ("dense_only", "keyword_only", "no_zscore", "dim_256")}
    print(f"   other variants: {alt}")

# Which unit kinds carried the top-1 hit on correct answers
kc = defaultdict(int)
for i in range(N):
    if V["baseline"][i]["rank"] == 1:
        kc["+".join(sorted(V["baseline"][i]["top"][0][2]))] += 1
print("\nUnit kinds matched in correct top-1 results:", dict(sorted(kc.items(), key=lambda x: -x[1])))
