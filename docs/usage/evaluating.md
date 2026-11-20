# Evaluating

`labrador eval` runs a file of labelled queries against an index and reports how often the right file comes first.
Use it to compare settings (`--dim`, vision token budgets, ranking changes) on the same folder. With `--answers` it
scores `labrador ask` instead; see [Answer quality](#answer-quality).

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

`labrador eval --answers` runs every question in a QA file through `labrador ask` and scores the answers. It takes
the same LLM flags as `ask` (`--model`, `--llm-url`, `--llm-extra`, `--ctx`, `-k`, `--images`, `--allow-remote-llm`) and
needs a running LLM runtime:

```bash
uv run labrador eval bench/data/qa.jsonl --answers --out evals/out/answers.json
uv run labrador eval bench/data/qa.jsonl --answers --model gemma4:e4b --out evals/out/answers-gemma.json
```

`bench/data/qa.jsonl` holds 27 questions over the benchmark's fictional `documents/` folder: ID and date lookups,
questions the files can't answer, near misses, a current and an expired passport, and a note with a planted wrong
number. The row fields are in `bench/make_bench.py`'s docstring.

| Column | Meaning |
|---|---|
| `em` | Answerable rows whose answer contains the expected value |
| `cite_hit` / `cite_prec` | A cited source is the right file / the share of citations that are |
| `false_ans` | An answer to an unanswerable row, or a planted or stale value anywhere in the answer |
| `false_ref` | A refusal on an answerable row |
| `unverif` | The verbatim check flagged an ID or date |
| `hit@5` | The right file was among the sources (separates retrieval misses from model misses) |
| `sec/q` | Seconds per question |

Under the table, `timings (ALL)` shows the p50 and p95 (nearest rank) of `retrieval_ms`, `answer_ms`, `ttft_ms` and
`tok_s` over the questions that have a value (`-` when none do; `ttft_ms` and `tok_s` need a runtime that reports
them). The `--out` file has the same numbers in `summary` (`retrieval_ms_p50`, ...) and each row's `timings`.

Scoring is deterministic and needs no LLM judge. It scores the streamed answer, the path `ask` shows. An LLM error
counts as a refusal on that row, and the command exits 1 at the end. The `--out` file also records the model, URL,
options and context size. [evals/answers/REPORT.md](../../evals/answers/REPORT.md) compares the default model
with the alternatives.

## Timing `ask`

`scripts/ask_bench.py` measures where an `ask` spends its time. `run` loads the embedder once (like `labrador serve`),
asks every question in a QA file with a `Trace` and scores the answers like `eval --answers`. It records the embedder's
load and first-embed times and, per question, the timings and span tree. `summary` then prints one row per run:
quality rates, p50/p95 of total, retrieval and query embedding, p50 of load+prefill, thinking, decode, first token,
runtime tokens per second and prompt tokens against the packer's estimate, and each stage's share of wall time.

```bash
uv run python scripts/ask_bench.py run bench/data/qa.jsonl --index <index dir> --tag gemma4 [--model M] [--extra '{"reasoning_effort": "none"}']
uv run python scripts/ask_bench.py summary evals/out/ask-bench
```

`run` also takes `--llm-url`, `--ctx`, `-k`, `--limit N` (first N questions) and `--out DIR` (default
`evals/out/ask-bench`). `summary` reads every `*.json` in its directory.

`run` writes `evals/out/ask-bench/<tag>.json`; `evals/out/` is gitignored, so keep raw results there. Set
`HF_HUB_OFFLINE=1` to stop the embedder retrying the Hugging Face Hub when the network is down. The span names and
fields are in [the design](../design/observability.md).
