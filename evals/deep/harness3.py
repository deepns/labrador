import random
import sys

src = open(sys.argv[4]).read().split("BASE = {}")[0]
exec(src)
P = {"mode": "and", "kw_weight": 1.0}
cfgs = {"baseline": {}, "dense_only": {"kw_weight": 0}, "proposed": P, "proposed_w0.7": {"mode": "and"}}
for nm, dk in {"no_ocr": ("image_ocr", "pdf_image_ocr", "pdf_ocr"), "no_image_vec": ("image", "pdf_page", "pdf_image"),
               "no_page_img": ("pdf_page",), "no_embedded_img": ("pdf_image", "pdf_image_ocr"),
               "text_only": ("image", "pdf_page", "pdf_image", "image_ocr", "pdf_image_ocr", "pdf_ocr")}.items():
    cfgs[f"proposed_{nm}"] = {**P, "drop_kinds": dk}
for d in (512, 256, 128):
    cfgs[f"proposed_dim{d}"] = {**P, "dim": d}
cfgs["proposed_no_zscore"] = {**P, "zscore": False}
R = {n: evaluate(c) for n, c in cfgs.items()}
rr = lambda r: 1 / r if r else 0
random.seed(0)
def ci(a, b):
    d = [rr(x) - rr(y) for x, y in zip(R[a], R[b])]
    bs = sorted(sum(d[random.randrange(N)] for _ in range(N)) / N for _ in range(5000))
    return sum(d) / N, bs[125], bs[4875], sum(x > 0 for x in d), sum(x < 0 for x in d)
cats = sorted({r.get("category", "-") for r in rows}); hard = [i for i, r in enumerate(rows) if r.get("hard")]
print(f"{'config':<26}{'h@1':>6}{'h@5':>6}{'MRR':>7}{'hard':>7}  dMRR vs proposed [95% CI] w/l")
for n, rs in R.items():
    m, lo, hi, w, l = ci(n, "proposed")
    print(f"{n:<26}{sum(r == 1 for r in rs)/N:>6.2f}{sum(bool(r) and r <= 5 for r in rs)/N:>6.2f}{mrr(rs):>7.3f}"
          f"{mrr([rs[i] for i in hard]):>7.3f}  {m:+.3f} [{lo:+.3f},{hi:+.3f}] {w}/{l}")
for a, b in (("proposed", "baseline"), ("proposed", "dense_only")):
    print(a, "vs", b, "dMRR %+.3f [%+.3f, %+.3f] wins/losses %d/%d" % ci(a, b))
print("\nPer-category proposed:", {c: round(mrr([R['proposed'][i] for i, r in enumerate(rows) if r.get("category", "-") == c]), 3) for c in cats})
print("Per-category proposed_dim256:", {c: round(mrr([R['proposed_dim256'][i] for i, r in enumerate(rows) if r.get("category", "-") == c]), 3) for c in cats})
print("Per-category proposed_no_image_vec:", {c: round(mrr([R['proposed_no_image_vec'][i] for i, r in enumerate(rows) if r.get("category", "-") == c]), 3) for c in cats})
print("Per-category proposed_no_ocr:", {c: round(mrr([R['proposed_no_ocr'][i] for i, r in enumerate(rows) if r.get("category", "-") == c]), 3) for c in cats})
print("\nStill not top-1 under proposed:")
for i, r in enumerate(rows):
    if R["proposed"][i] != 1:
        print(f"  rank={R['proposed'][i]} base={R['baseline'][i]} [{r.get('category', '-')}{' HARD' if r.get('hard') else ''}] {r['query']!r} -> {r['expect']}{' p'+str(r['page']) if r.get('page') else ''}")
print("\nRegressions vs baseline:")
for i, r in enumerate(rows):
    if rr(R["proposed"][i]) < rr(R["baseline"][i]):
        print(f"  {R['baseline'][i]} -> {R['proposed'][i]}  [{r.get('category', '-')}] {r['query']!r}")
print("\nkw hits under AND per query (nonzero):", sum(bool(keyword(r['query'], mode='and')) for r in rows), "of", N)
print("text-exact AND hits:", [(r['query'], len(keyword(r['query'], mode='and'))) for r in rows if r.get("category", "-")=='text-exact'])
