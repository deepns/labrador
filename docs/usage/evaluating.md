# Evaluating

`labrador eval` runs a file of labelled queries against an index and reports how often the right file comes first.
Use it to compare settings (`--dim`, vision token budgets, ranking changes) on the same folder.

```bash
uv run labrador index ~/labrador-sample
uv run labrador eval evals/sample_queries.jsonl
```

## The query file

One JSON object per line:

```json
{"query": "dessert made with overripe fruit", "expect": "banana-bread"}
{"query": "are dogs allowed in the apartment", "category": "pdf-text-page", "expect": "pdfs/lease-maple-court-unit-4B.pdf", "page": 3, "hard": true}
```

| Field | Meaning |
|---|---|
| `query` | What you would type into `search` |
| `expect` | A substring of the right file's path (case-insensitive) |
| `page` | Optional: the hit must also be this PDF page |
| `also` | Optional: other paths that count as correct, matched by file only |
| `category` | Optional: groups the scores in the report |
| `hard` | Optional: a hard negative (a near-duplicate file sits in the folder); scored as its own row too |

## Reading the report

Each query prints a line: `✓` when the right file ranks first, `@3` when it ranks third, `✗` when it isn't in the
top 10, followed by the category, the query and the top hit. Then a table:

```text
category               n  hit@1  hit@5  MRR@10
pdf-text-page         nn   0.xx   0.xx   0.xxx
scanned               nn   0.xx   0.xx   0.xxx
...
(hard negatives)      nn   0.xx   0.xx   0.xxx
ALL                  114   0.xx   0.xx   0.xxx
```

- **hit@1**: share of queries whose right file ranks first.
- **hit@5**: share with the right file in the top 5.
- **MRR@10**: mean of 1/rank over the top 10 (0 when it's missing). 1.0 means always first; 0.5 means second on
  average.

Every query searches with `k=10` and no `--only` filter, so the score matches what `search` shows by default.

## Options

| Flag | Effect |
|---|---|
| `--category X` | Only queries whose `category` is `X` |
| `--quiet` | Only the summary table |
| `--out FILE` | Write the summary and per-query results (rank, top hit) as JSON |
| `--index DIR` | Evaluate a different index |

Write `--out` files to `evals/out/`, which git ignores.

## The benchmark

`bench/make_bench.py` builds a fictional 126-file personal folder with 114 labelled queries in 13 categories,
including hard negatives. It needs the `sample` and `docs` extras and is deterministic:

```bash
uv run python bench/make_bench.py bench/data
uv run labrador index bench/data/folder
uv run labrador eval bench/data/queries.jsonl --out evals/out/before.json
```

To compare a change, index and evaluate before and after with the real model and diff the two `--out` files;
[evals/deep/REPORT.md](../../evals/deep/REPORT.md) is a worked example.
The fake backend (`--backend fake`) runs the harness but says nothing about quality.

A change in settings that affects vectors (`--dim`, `--image-tokens`, `--page-image-tokens`, `--dtype`) needs
`--rebuild`, or the two runs will mix old and new vectors:

```bash
uv run labrador index bench/data/folder --rebuild --dim 256
uv run labrador eval bench/data/queries.jsonl --quiet --out evals/out/dim256.json
```

## Answer quality

`labrador eval --answers` (scoring `labrador ask` against `bench/data/qa.jsonl`) is coming in a later release.
