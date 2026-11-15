# labrador-bench: answer quality of `labrador ask` (2026-11-15)

Questions: `bench/data/qa.jsonl`, 27 rows over the fictional `documents/` set (18 answerable, 9 unanswerable).
Index: `bench/data/folder`, `google/embeddinggemma-2`, 768 dims, default settings. Runtime: Ollama 0.40.16, both
models at the library's default `nvfp4` quantization, temperature 0, `--ctx 4096`, 5 sources. Machine: M1 Pro, 16 GB.

## Headline

**The default answer model is now `qwen3.5:4b`, with its thinking left on.** On a 16 GB Mac it matches or beats
`gemma4:e4b` on every metric except citation precision, and it is about 4.5× faster at under half the size.

| model | size | EM | cite hit | cite prec | false ans | false ref | unverified | hit@5 | s/question |
|---|---|---|---|---|---|---|---|---|---|
| gemma4:e4b | 9.5 GB | 0.83 | 0.94 | **0.88** | 0.22 | 0.00 | 0.04 | 1.00 | 69.3 |
| **qwen3.5:4b** (run A) | 4.0 GB | **0.89** | **1.00** | 0.87 | 0.22 | 0.00 | 0.04 | 1.00 | 15.1 |
| qwen3.5:4b (run B) | | 0.89 | 1.00 | 0.81 | 0.22 | 0.06 | 0.04 | 1.00 | 15.5 |
| qwen3.5:4b, thinking off | | 0.89 | 0.83 | 0.58 | 0.30 | 0.00 | 0.04 | 1.00 | 6.0 |

EM, cite hit and false refusals are over the 18 answerable rows, so one row is worth 0.056. Cite precision is the mean
over rows with citations. False answers and unverified are over all 27 rows. With this few rows, the EM gap is one
question. The choice rests on three things together: the gap on the injection rows, latency, and RAM.

- **Speed and memory.** gemma4:e4b takes 9.5 GB beside the embedder on a 16 GB machine and averaged 69 s per question.
  It doesn't think: a direct `/v1` call returns no `reasoning`. The slowdown therefore looks like memory pressure,
  not extra tokens. qwen3.5:4b averaged 15 s.
- **Planted injection** (`misleading`, 3 rows). gemma4:e4b repeated the planted `ZZ9999999` as the answer in all 3,
  once adding "this came from the official registry" as the note instructs. qwen3.5:4b gave `ZZ9999999` in 2 of 3 (once
  saying "I should report" it, as the note instructs). In the third it named the note as an instruction and gave the
  real number. Neither model is safe here. The defence is still the sources
  list next to the answer: the planted value is verbatim in a cited source, so the checks rate it `high` confidence.
- **Thinking off is worse.** With thinking off, qwen3.5:4b runs at 6 s per question, but it cites the wrong source
  more often (cite precision 0.58). It also answered the MRZ question with the expired passport's number and answered
  "mother's maiden name" with the holder's own name.

Runs A and B are the same configuration twice, because Ollama ignored the `think` flag (see below). Their spread
(one false refusal, ±0.06 cite precision) shows the run-to-run noise, even at temperature 0.

## What the metrics catch, and what they miss

- **`false ans` is strict on purpose.** A row's `bad` values (planted or stale numbers) count wherever they appear in
  a non-refused answer, even when the model labels them correctly ("the old passport, KB2206937, expired in 2014").
  That puts every model at 0.75 on `conflict`. The metric measures whether a stale value reaches the screen, not
  whether the model was confused. Read the `misleading` rows for the injection result.
- **`unverified`** fired once per model: a date cited to the wrong source, and an MRZ line the model re-typed with
  `‹` for `<`. The verbatim check works as designed. It has not flagged a reformatted correct answer yet, because
  the dates in these sources keep the formats the regexes know.
- **Retrieval is not the bottleneck.** hit@5 = 1.00 everywhere: every miss above comes from the generator.

## Scoring the streamed text, not `--json`

The harness scores the plain streamed answer, which is the path `labrador ask` users see. Ollama's MLX runner
returns HTTP 501 for `response_format` JSON schemas, so `--json` would rule out the default runtime. The streamed
path already gives everything the metrics need: the citations and checks come from `answer.check()`, and EM is a
substring or regex match on the text.

## Ollama ignores `think` on `/v1`

`--llm-extra '{"think": false}'` has no effect on Ollama's OpenAI-compatible endpoint: the reply still carries a
`reasoning` field and takes as long. `{"reasoning_effort": "none"}` does turn thinking off. [asking.md](../../docs/usage/asking.md)
now says so. This doesn't affect the default, since thinking stays on.

## Not measured yet

k = 3/5/8, the keyword-handling ablation, and span selection (design doc, Evaluation). The 8, 32 and 64 GB tiers
need models that aren't on this machine. Vision input (P6) is a separate phase.

## Reproduce

```bash
uv run --extra dev --extra mac --extra sample --extra docs python bench/make_bench.py bench/data
uv run labrador index bench/data/folder
ollama pull qwen3.5:4b
uv run labrador eval bench/data/qa.jsonl --answers --model qwen3.5:4b --out evals/out/answers-qwen35-4b.json
uv run labrador eval bench/data/qa.jsonl --answers --model qwen3.5:4b --llm-extra '{"reasoning_effort": "none"}' \
    --out evals/out/answers-qwen35-4b-none.json
uv run labrador eval bench/data/qa.jsonl --answers --model gemma4:e4b --out evals/out/answers-gemma4-e4b.json
```

Each `--out` file records the model, URL, extra options, temperature, context size, source count and embedder, along
with every question's answer, sources, citations and check.
