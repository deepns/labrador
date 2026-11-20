# Design: timings for search and ask

Status: **O1 to O3 done; O4 deferred** (see [Rollout](#rollout)). Research: [reports/Observability for retrieval and generation.md](../../reports/Observability%20for%20retrieval%20and%20generation.md).

When an answer takes eight seconds, labrador can't say where the time went today. This design adds timings to
`labrador search` and `labrador ask`, in the CLI and in the web UI. A few top-level numbers show on every answer:
how long retrieval took, how long the answer took, the time to first token, tokens per second and token counts. A
per-stage breakdown appears with `--trace`. A ~50-line recorder, `trace.py`, holds the timings in memory for the length of one
request. Nothing is written to disk and no new dependency is added.

## Goals

- Every answer shows where its time went: retrieval vs. answer, time to first token, decode speed, prompt and
  completion tokens.
- `--trace` shows each stage underneath (vector load, query embedding, keyword search, packing, lock waits), so a
  slow request can be debugged without a profiler.
- Measure the real prompt size the runtime saw, to check labrador's chars/4 budget, and flag answers cut off by
  `llm_max_tokens`. Both are open risks in [ask.md](ask.md#risks-and-open-questions).
- The same numbers in the CLI, `ask --json`, the web UI and `eval --answers`.
- Every timed stage stays a visible `with trace.span(...)` in the code it times.

## Non-goals

- No log of timings on disk, opt-in or otherwise. One row per question would be a usage log, and
  [ask.md](ask.md#non-goals) rules out a question log. `eval` output in `evals/out/` covers regression tracking.
- No OpenTelemetry, Prometheus or other exporter (see [Decisions](#decisions)).
- No timings for indexing yet. Tracked in [#27](https://github.com/deepns/labrador/issues/27).
- No profiling inside the model call. `embed_query` is timed as one span. MPS runs asynchronously, so spans inside
  `encode` would be wrong.

## What is shown

### By default

`labrador ask`, after the existing status line, on **stderr** so that stdout stays the answer:

```
✓ verified against [1] · high confidence
retrieval 0.21 s · answer 4.8 s · first token 1.2 s · 38 tok/s · 3,480 → 182 tokens
```

`labrador search` prints `12 results in 0.18 s` on stderr. `search --json` keeps its current shape (a list of hits) on
stdout.

The web UI shows the same line, in muted text, under the answer's status line.

### With `--trace`

`ask --trace` and `search --trace` also print the span tree on stderr:

```
trace                                   5021 ms
  keywords                                  3 ms  n_hits=0 fallback=1
  attempt 1                              5015 ms
    retrieve                              205 ms
      matrix                                1 ms  cache_hit=1 n_units=5120
      embed_query                          41 ms
      dense                                 3 ms  pool=300
      keyword                               2 ms  n_hits=14
      collapse                              4 ms  n_candidates=312 n_results=10
      enrich                                9 ms  n_queries=10
    pack                                    9 ms  n_sources=5 est_tokens=3100 n_truncated=0 n_dropped=1
    generate                             4790 ms  headers_ms=310 first_chunk_ms=402 ttft_ms=1190 n_chunks=183
    check                                   1 ms
```

`labrador serve --trace` adds the same tree to the web responses (see [Web protocol](#web-protocol)).

### Metric definitions

| Metric | Definition |
|---|---|
| `retrieval_ms` | Time spent in every `keywords`, `retrieve` and `pack` span, wherever it sits in the tree (including the retry's `keywords`). |
| `answer_ms` | Time spent in `generate`, summed over attempts. |
| `total_ms` | Wall clock for the whole `ask()`, including `check` and retry bookkeeping. |
| `ttft_ms` | From the start of the **final** attempt's `generate` to its first non-empty `delta.content`. `null` for `--json` (non-streamed). |
| `prompt_tokens`, `completion_tokens` | From the final attempt's `usage` object, as the runtime reports it. `null` when the runtime doesn't send one. Never estimated. |
| `tok_s` | `completion_tokens / (end − first content token)` of the final attempt: decode speed only, without prefill. If the runtime sends its own decode rate (llama.cpp's `timings.predicted_per_second`), that wins. `null` when either input is missing. |
| `cut_off` | The final attempt's `finish_reason == "length"`: the answer hit `llm_max_tokens`. |
| `attempts` | 1, or 2 when the rarest-term retry ran. |

Metrics that are `null` are left out of the CLI and web line rather than shown as zero. When `cut_off` is true, the
CLI adds a warning, `the answer was cut off at llm_max_tokens (2048)`; the web line says the same without the number.

Per-attempt values (ttft, tokens) describe the answer the user sees. Summed values (retrieval, answer) describe how
long the user waited.

## Architecture

```
cli.py / web.py ── creates Trace ──► answer.ask(…, trace) ──► search.search(…, trace)
                                          │                       └► store / embedder (timed by search)
                                          └──────────────────────► llm.stream(…, trace) / complete(…, trace)
      ◄── events carry trace.summary() (and trace.tree() with --trace)
```

One new module, `labrador/trace.py`. `search()`, `ask()`, `OpenAICompatLLM.stream()/complete()` and `FakeLLM` take
an optional `trace` argument that defaults to `NOOP`. Callers that pass nothing (tests, `eval`, the bench scripts)
behave exactly as before.

### `trace.py`

```python
SPANS = {"attempt", "keywords", "retrieve", "matrix", "lock_wait", "embed_query", "dense", "keyword",
         "collapse", "enrich", "pack", "picture", "generate", "check"}

class Trace:
    def span(self, name, **attrs)   # context manager: perf_counter in/out, pushes a child node; name must be in SPANS
    def set(self, **attrs)          # attach attributes to the innermost open span
    def summary(self) -> dict       # the metrics table above
    def tree(self) -> dict          # {"name", "ms", "attrs", "children"}; for --trace
    def render(self) -> str         # the indented text tree

NOOP                                # same interface, records nothing
```

**Attributes are numbers, booleans or `None`.** `span()` and `set()` raise `TypeError` on any other type, and
`span()` raises `ValueError` on a name outside `SPANS`. This is the privacy rule in code. No question, keyword,
term, path, snippet or model output can reach a trace, so none can reach a terminal, the `Server-Timing` header or a
pasted bug report.

### Why an explicit argument, not a context variable or `llm.last_usage`

- `ask()` is a generator. In `serve`, Starlette's `StreamingResponse` advances it from a thread pool, one `next()` at
  a time, each in a copied context. A `contextvars` value set inside the generator isn't reliably visible on the
  next step.
- `serve` shares one `OpenAICompatLLM` across concurrent requests, so per-call state on the client object (a
  `last_usage` attribute) would race.
- The argument is also easier to follow, which matters in a learning codebase.

## Spans

These are the instrumentation points. Each is a `with trace.span(...)` around code that already exists.

| Span | Module, code | Attributes |
|---|---|---|
| `attempt` | `answer.ask()`, each pass of `while True` | `n` (1 or 2) |
| `keywords` | `answer.ask()`: the first `store.keyword(kw)` + `rarest_term()`, which run *before* the `while True` loop (a sibling of `attempt`); and again, inside the attempt, around the retry's `rarest_term()` after `check()` | `n_hits`, `fallback` |
| `retrieve` | `answer.retrieve()` | — |
| `matrix` | `search()`, `store.matrix()` | `cache_hit`, `n_units` |
| `lock_wait` | `web.py`, acquiring `model_lock`: in `LockedEmbedder` (ask, O2) and in `_search` (`/api/search`, O3) | — |
| `embed_query` | `search()`, `emb.embed_query()` | — |
| `dense` | `search()`, matmul + per-modality z-score + argsort | `pool` |
| `keyword` | `search()`, `store.keyword()` | `n_hits` |
| `collapse` | `search()`, `store.units()` + group loop | `n_candidates`, `n_results` |
| `enrich` | `search()`, the `group_units()` loop | `n_queries` (one SQL query per hit) |
| `pack` | `answer.pack()` | `n_sources`, `est_tokens`, `n_truncated`, `n_dropped` |
| `picture` | `answer.pack()`, each `load_picture()` | — |
| `generate` | `llm.stream()` / `complete()` | `headers_ms`, `first_chunk_ms`, `ttft_ms`, `n_chunks`, `prompt_tokens`, `completion_tokens`, `cut_off`, plus llama.cpp's `timings` numbers as `rt_*` when present |
| `check` | `answer.ask()`, `check()` + the quote check | — |

`store.matrix()` needs a small change: it returns whether the cache was hit (or exposes it as an attribute) so
`search()` can record `cache_hit`.

`lock_wait` is recorded in two places, because the two routes take `model_lock` differently. `api_ask` builds a
`LockedEmbedder` per request, which locks only around `embed_*` calls; it takes the request's trace and times the
acquire. `_search` holds `model_lock` itself around the whole `search()` call (matrix, dense and enrich included);
it times the acquire directly, before `search()` opens its own spans. `/api/search` records it only with
`serve --trace`, and reports it in `Server-Timing`.

### Generation details

`stream()` sends `"stream_options": {"include_usage": true}` and reads the final usage chunk, which the loop
currently skips (`if not chunk.get("choices"): continue`). It records:

- `headers_ms`: time until `client.stream()` returns. This is model load and queueing; a cold model after
  `keep_alive` expires shows up here.
- `first_chunk_ms`: first `data:` line.
- `ttft_ms`: first non-empty `delta.content`. A large gap after `first_chunk_ms` means the model is thinking:
  reasoning chunks carry no `content`.
- `finish_reason` from the last choice chunk, giving `cut_off`.
- `usage` and, if present, llama.cpp's `timings` object, copied as numbers. The code doesn't branch on the runtime's name.

`complete()` reads `usage` and `finish_reason` from the single response body. It has no `ttft_ms`.

`FakeLLM` records `n_chunks` and reports `completion_tokens = n_chunks` and `prompt_tokens = chars/4` of the
messages, so tests can check the plumbing end to end.

### Streamed spans include consumer time

`ask()` yields deltas while `generate` is open, so `answer_ms` also counts the time the consumer takes to handle each
delta: CLI printing, or the socket to the browser. Locally that is negligible. Read `answer_ms` as "until the last
token reached the consumer", not "until the runtime finished". The runtime's own numbers (`rt_*`), when present, are
the server-side view.

## Event and output changes

`ask()` events gain fields. No existing field changes:

| Event | New field |
|---|---|
| `sources` | `retrieval_ms`: this attempt's keywords + retrieve + pack, so the UI can show it while generation runs |
| `done` | `timings`: `trace.summary()`; and `trace`: `trace.tree()` only when tracing |

`ask()` takes `trace` from its caller and adds `trace.tree()` to `done` only if the caller asked (`include_tree`).
The CLI and web decide that from `--trace`.

`ask --json` output gains `"timings"` always and `"trace"` with `--trace`.

`eval --answers` rows gain `timings` next to the existing `seconds`. Its summary gains p50 and p95 of `retrieval_ms`,
`answer_ms`, `ttft_ms` and `tok_s`.

## Web protocol

```
{"type":"sources","sources":[…],"warnings":[],"retrieval_ms":212}
{"type":"delta","text":"Your passport number is "}
{"type":"done","check":{…},"retried":false,
 "timings":{"retrieval_ms":212,"answer_ms":4810,"total_ms":5021,"ttft_ms":1190,"tok_s":38.2,
            "prompt_tokens":3480,"completion_tokens":182,"cut_off":false,"attempts":1}}
```

`app.js` renders `timings` as one muted line under the status line, built with `textContent` like everything else.
`_ndjson` passes the new fields through unchanged. They hold only numbers, so masking doesn't apply.

With `serve --trace`:

- `done` also carries `"trace": {…tree…}`. The page doesn't render it; it is visible in the devtools Network panel.
- `GET /api/search` responses carry a
  [`Server-Timing`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Server-Timing) header, e.g.
  `lock_wait;dur=0, matrix;dur=1, embed_query;dur=41, dense;dur=3, keyword;dur=2, collapse;dur=4, enrich;dur=9`. Its names come
  only from `SPANS`. Without `--trace` the header is not sent.

`/api/ask` gets no `Server-Timing`. Its headers go out before the work is done, and browsers don't surface
`Server-Timing` sent as a trailer.

## Security and privacy

- Traces live in memory for one request and are dropped with it. Nothing is written to disk.
- `trace.py` rejects string attributes and unknown span names, and a test checks it. No user content can enter a
  trace.
- Timings in the web response can show how long a request took, and so roughly how large the matched files were.
  The web UI is loopback-only by default, and the response already contains the sources themselves.
- `stream_options` is a request field sent to the loopback runtime. It carries no user data.

## Testing

All on `FakeEmbedder` and `FakeLLM`, so no model download:

- `trace.py`: nesting, `summary()` math (sums across attempts, final-attempt ttft and tokens, `null` handling),
  `TypeError` on a string attribute, `ValueError` on an unknown span name, `NOOP` records nothing.
- `ask()` with a trace: every expected span appears once per attempt; a forced retry gives `attempts=2` and summed
  `retrieval_ms`; `sources.retrieval_ms` and `done.timings` are present; `done.trace` only with `include_tree`.
- `OpenAICompatLLM` against a stub transport (`httpx.MockTransport`): `include_usage` is sent; the usage chunk is
  read; `finish_reason: "length"` sets `cut_off`; a stream with no usage gives `null` tokens; llama.cpp `timings`
  become `rt_*` attributes.
- CLI: the default metrics line is on stderr and omits `null` metrics; `--trace` prints the tree; `ask --json`
  carries `timings`.
- Web (`tests/test_web_ask.py`, `tests/test_web.py`): `done.timings` and `sources.retrieval_ms` present; `Server-Timing` present only with `--trace` and contains only
  `SPANS` names.
- Benchmark: `scripts/ask_bench.py` (outside the O phases) times `ask` per stage over a QA file; see
  [Timing `ask`](../usage/evaluating.md#timing-ask).
- Manual (O2): `labrador serve` on `~/labrador-sample`, ask in the browser with the console open, and attach
  screenshots of the timings line, per CLAUDE.md.

## Decisions

- **Hand-rolled recorder, no OpenTelemetry.** OpenTelemetry means several packages and an exporter that sends data
  over the network. Its GenAI conventions are still *Development*, and common LLM instrumentations record prompts
  by default. If ever wanted, a ~30-line adapter can replay `Trace.tree()` into OTel spans.
- **Top-level metrics by default, per-stage breakdown behind `--trace`.** The default line explains a slow answer
  in one glance; the tree is for debugging.
- **No log on disk.** See [Non-goals](#non-goals).
- **Explicit `trace` argument.** See [Why an explicit argument](#why-an-explicit-argument-not-a-context-variable-or-llmlast_usage).
- **Token counts come from the runtime or not at all.** labrador's chars/4 estimate is what is being checked, so it
  can't stand in for the real count.
- **Metrics on stderr.** stdout stays the answer (and the existing status line), so `labrador ask … > answer.txt`
  isn't cluttered.

## Risks and open questions

- **Ollama's usage chunk.** Verified on Ollama 0.40.16: the final chunk has `"choices": []` with `usage` (prompt and
  completion tokens) and a llama.cpp-style `timings` object (including `predicted_per_second`), then `data: [DONE]`.
- **A runtime may reject `stream_options`.** OpenAI-compatible servers usually ignore unknown fields, but not all do.
  `--llm-extra` merges over the request body, so today it can only replace the field with `null`, not remove it.
  Still open after O1 (only Ollama is checked): check llama.cpp, LM Studio and `mlx_lm.server`, then decide between dropping `null` values from
  `llm_extra` and retrying once without `stream_options` on a 4xx.
- **`answer_ms` includes consumer time** (see [above](#streamed-spans-include-consumer-time)). Fine locally; worth
  knowing before comparing web and CLI numbers.
- **`tok_s` excludes prefill** by definition. Runtimes that report a combined rate will differ; the trace keeps both.
- **Overhead is assumed negligible.** About 15 `perf_counter` calls per request. Unmeasured: compare `eval` latency
  with and without a trace in O1 to confirm.

## Rollout

Each row is one PR, within about 400 changed lines, with its tests and doc updates.

| Phase | Scope | Needs | Est. lines | Status |
|---|---|---|---|---|
| O1 | `trace.py`; spans in `search()`, `answer.ask()`, `llm.stream()/complete()` incl. `include_usage` and `cut_off`; `FakeLLM` usage; CLI default metrics line for `ask` and `search`; `ask --json` `timings`; tests; `usage/asking.md` and `usage/searching.md` | | ~300 | done |
| O2 | Web: `retrieval_ms` on `sources`, `timings` on `done`, the line in `app.js`; `LockedEmbedder` `lock_wait`; `tests/test_web_ask.py`; `usage/web-ui.md` | O1 | ~150 | done |
| O3 | `--trace` for `ask`, `search` and `serve` (text tree, `done.trace`, `Server-Timing`, `_search` `lock_wait`); `eval --answers` timings and p50/p95; `reference/cli.md` | O1, O2 | ~200 | done |
| O4 | Indexing timings ([#27](https://github.com/deepns/labrador/issues/27)) | O1 | ~100 | deferred |
