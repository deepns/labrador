# labrador-bench: deep retriever evaluation (2026-10-25)

Index: `bench/data/folder` (120 files, 288 units), `google/embeddinggemma-2`, 768 dims, float32 on MPS,
default settings (`image_tokens=280`, `page_image_tokens=560`, Apple Vision OCR). 114 queries, 13 categories,
23 hard-negative queries. Machine: M1 Pro, 16 GB.

## Headline

**The keyword (BM25) branch is the main source of error.** In 24 of the 32 baseline misses (rank ≠ 1) the right
unit is already #1 by raw cosine, and RRF fusion with the keyword list pushes it down. Changing the keyword match
from OR to **AND** (every query term must appear in the unit) and raising `keyword_weight` to 1.0 gives:

| | hit@1 | hit@5 | MRR@10 | hard negatives MRR |
|---|---|---|---|---|
| current (`OR`, w=0.7) | 0.72 | 0.84 | 0.783 [0.712, 0.849] | 0.783 |
| dense only (no keywords) | 0.86 | 0.98 | 0.914 | 0.906 |
| **proposed (`AND`, w=1.0)** | **0.90** | **1.00** | **0.947** | 0.906 |

Proposed vs current: ΔMRR **+0.164** [95% paired-bootstrap CI +0.091, +0.240], 27 queries better / 8 worse.
Proposed vs dense only: +0.033 [+0.007, +0.066], 5 better / 0 worse.

Overfitting check: a 290-config grid (stop-words, phrase tokens, OR/AND/AND-then-OR, keyword top-N, weight,
RRF k) chosen on one stratified half and scored on the other, 40 folds: **held-out MRR 0.929 ± 0.025**,
against 0.783 for the current config on the same halves. AND matching was picked in 37 of the 40 folds.

### Applied (same day)

`Store.keyword` now ANDs the query words, `search()` defaults to `keyword_weight=1.0`, and `torchvision` is
a dependency. Confirmed with the real CLI, no re-index needed (`labrador eval … --out
evals/out/results-after-fix.json`, see Reproduce): hit@1 0.90, hit@5 1.00, MRR 0.947, with the same 11 near-misses predicted
above. On the separate `evals/sample_queries.jsonl` set (12 queries, generated sample folder, not used to choose
the fix), MRR goes from 0.747 to 1.000.

## Per category (MRR@10)

| category | n | current | dense only | proposed |
|---|---|---|---|---|
| multilingual | 5 | **0.050** | 1.000 | 1.000 |
| image-visual | 17 | **0.456** | 1.000 | 1.000 |
| pdf-visual-page | 3 | 0.667 | 1.000 | 1.000 |
| pdf-embedded-image | 4 | 0.750 | 1.000 | 1.000 |
| image-ocr | 12 | 0.842 | 1.000 | 1.000 |
| text-exact | 9 | 0.852 | **0.528** | 0.944 |
| text-semantic | 37 | 0.878 | 0.849 | 0.849 |
| pdf-text-page | 11 | 0.909 | 1.000 | 1.000 |
| code, docx-text, docx-image, scanned, needle | 16 | 1.000 | 1.000 | 1.000 |

## Why the keyword branch hurts

1. **Asymmetric candidates.** In `units_fts`, image units (`image`, `pdf_page`, `pdf_image`) have empty text and
   match only by file name. Text units match on any shared word. `Store.keyword` ORs every query word,
   stop-words included, so a natural-language query returns 4–200 units (median 121; 200 is the limit), and each one
   gains RRF score that pictures and non-English files cannot gain. RRF arithmetic: dense #1 alone scores
   1/61 = 0.0164, but a text unit at dense #20 plus keyword #1 scores 1/81 + 0.7/61 = 0.0238. That is why the
   failing categories are exactly the ones whose answers share no words with the query: multilingual files,
   pictures, and page renders.
2. **Identifiers get split.** `LD-2026-0417` becomes `ld OR 2026 OR 0417`; "2026" matches 161 units.

AND matching fires on only 8 of the 114 queries, nearly all of them the ID-style ones, which then get exact hits.
Long questions get no keyword hits, so they are ranked by dense scores alone. The weaker fixes I tried
(stop-word removal, phrase tokens, top-N caps, lower weights, AND-then-OR) all keep the OR tail and recover
only part of the gap (MRR 0.79–0.88).

**Cost of the fix:** in 8 text-semantic queries, OR keywords had lifted the answer from #2 to #1 (`how long was
checkout down in March`, `binary search through history…`). Under the proposed config they drop to #2–#4. All 11
remaining non-top-1 queries are near misses within the top 4. 10 of them are text-semantic, and 5 of those are
hard negatives (two postmortems, two Kubernetes notes, espresso notes vs manual). The 11th is `K7Q2ZP`, below.

## Ablations (on the proposed config)

| change | MRR | Δ vs proposed [95% CI] | reading |
|---|---|---|---|
| no image vectors (text + OCR only) | 0.876 | −0.071 [−0.129, −0.016] | image vectors matter: image-visual 1.00 → 0.55 |
| text units only (no images, no OCR) | 0.646 | −0.300 [−0.392, −0.212] | |
| no OCR units | 0.936 | −0.011 [−0.029, +0.006] | not significant: image vectors already read text (scanned 1.00 → 0.83, exact 0.94 → 0.87) |
| no PDF page images | 0.955 | +0.008 [−0.018, +0.034] | not significant either way at n=3 visual-page queries |
| no embedded PDF images | 0.937 | −0.009 [−0.037, +0.014] | not significant |
| no per-modality z-score | 0.958 | +0.011 [−0.016, +0.039] | **z-scoring shows no measurable benefit here** |
| dim 512 | 0.954 | +0.008 [−0.013, +0.030] | free |
| dim 256 | 0.944 | −0.002 [−0.018, +0.014] | free, and the index is 3× smaller |
| dim 128 | 0.887 | −0.059 [−0.098, −0.026] | real loss |
| `max_per_file` 1 or 5 (current config) | 0.780 / 0.786 | ±0.003 | no effect |

Under the current config, removing OCR looked catastrophic (−0.156). That came from the keyword noise: OCR text
was the only way images could compete in the OR list. Once that noise is gone, the vision encoder carries most
of the load.

## Other findings

- **Missing dependency.** `torchvision` is required by `EmbeddingGemma2VideoProcessor` but is not in
  `pyproject.toml`, so `check_model.py`, `labrador index` and the README quick start all fail on a fresh
  `uv sync`. This evaluation ran with `uv run --with torchvision`. (Now fixed in `pyproject.toml`.)
- **OCR misread.** The boarding-pass code `K7Q2ZP` was read as `K7QZZP`, so exact match cannot find it. It still
  ranks #2 by image vector. Character-trigram FTS (`tokenize='trigram'`) would tolerate this kind of error.
- **Hindi greeting card**: Vision OCR returned no text, but the image vector alone ranks it #1 under the
  proposed config.
- **Kind label for DOCX pictures.** Embedded DOCX pictures are stored as `pdf_image`, so `--only pdf` returns
  them and `--only image` does not.
- **README tuning advice.** Raising `keyword_weight` for ID-heavy folders does not help under OR matching
  (1.0 → MRR 0.778, 1.5 → 0.777, exact 0.889). It only helps once matching is AND.
- **Performance.** Indexing took 193 s for 120 files / 7.8 MB, with 2.0 GB peak RSS and a 4.4 MB index.
  Image throughput is about 1.6 images/s at 280 tokens, and PDF page renders dominate the time. A query takes
  about 35–50 ms including the query embedding.

## Caveats

- 114 queries: categories with n ≤ 5 swing by 0.2 MRR per query, so read them as anecdotes. The overall
  and cross-validated numbers are the reliable ones.
- The photos are drawn scenes, and the folder has 120 files. A real folder has many more text units, so OR-mode
  noise is likely worse, while AND mode on short queries ("tax 2024") will match more units than here.
- Hit criterion: the expected path substring (and page, when given) appears in the top 10 grouped results.
- Matryoshka dims were simulated by truncating and re-normalising stored 768-d vectors, which is what
  `truncate_dim` + `normalize_embeddings` does.

## Reproduce

```bash
# from the repo root; benchmark generated with: uv run python bench/make_bench.py bench/data
# raw outputs go to evals/out/ (gitignored)
uv run --with torchvision labrador index bench/data/folder
IDX=$(uv run python -c "from pathlib import Path; from labrador.config import index_dir_for; print(index_dir_for(Path('bench/data/folder')))")
Q=bench/data/queries.jsonl
mkdir -p evals/out
uv run --with torchvision python evals/deep/harness.py  $IDX $Q evals/out/results-768.json    # 19 variants, checks reimpl == search()
python3 evals/deep/analyze.py evals/out/results-768.json
uv run --with torchvision python evals/deep/harness2.py $IDX $Q evals/out/results-round2.json # keyword fixes + CV grid
uv run --with torchvision python evals/deep/harness3.py $IDX $Q /dev/null evals/deep/harness2.py  # CIs, ablations
uv run labrador eval $Q --out evals/out/results-after-fix.json                                 # applied fix, real CLI
```

`harness.py` reproduces `labrador.search.search` exactly (0 / 114 mismatches) before any variant is measured.
