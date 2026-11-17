# Observability for retrieval and generation

**Recommendation.** Add one small, dependency-free module, `labrador/trace.py` (about 50 lines), that records nested
timing spans with `time.perf_counter()`. Pass a `Trace` object explicitly through `search()`, `ask()` and the LLM
client. Show two headline numbers by default, **retrieval time** and **generation time** (with time to first token
and tokens/s), in the CLI status line, in `ask --json` and on the web UI's `done` event. Put the full span tree behind
an opt-in `--trace` flag for debugging. Record only stage names, durations, counts and sizes. Never record question
text, paths, snippets or model output, so the design's "no question log" rule still holds. Leave OpenTelemetry out
for now. It is a heavy dependency, its GenAI conventions are still unstable, and common LLM instrumentations capture
prompts by default. An exporter can be added later if it is ever wanted.

## What labrador measures today

Almost nothing, and what exists is scattered:

| Where | What | Gap |
|---|---|---|
| `indexer.run()` | total seconds for an index run | no per-file or per-stage split (extract / OCR / embed / write) |
| `cli.cmd_eval_answers` | wall seconds per question (`seconds`) | one number; retrieval and generation are not separated |
| `evals/deep/harness*.py` | mean query-embed and search ms | one-off scripts, not in the product |
| `llm.py` | `time.monotonic()` for the `llm_deadline_s` cap | used for enforcement, not reported |
| `search()` / `answer.py` / `web.py` | nothing | — |

## Where the time goes (what to instrument)

These spans come from reading the code. They are not measurements yet. Each is one `with trace.span(...)` around code
that already exists.

**Retrieval** (`search.search`, shared by `labrador search`, `/api/search` and `ask`):

| Span | Code | Why it matters |
|---|---|---|
| `matrix` | `store.matrix()` | Usually a cache hit. After any index change (including `watch`) it re-reads **every** vector from SQLite. Record `cache_hit` and `n_units`. This is the likely cause of an occasional slow first query. |
| `lock_wait` | `web.LockedEmbedder` (ask) and `with model_lock:` in `web._search` (search) | In `serve`, a query can wait behind another search or an ask's retrieval. Without this span, waiting looks like slow embedding. |
| `embed_query` | `emb.embed_query()` | Model forward pass on MPS/CPU. `convert_to_numpy` forces a device sync, so the wall time is accurate. Finer spans *inside* `encode` would not be (MPS runs asynchronously). |
| `dense` | matmul + per-modality z-score + argsort | Scales with the number of units. Cheap now, worth watching as indexes grow. |
| `keyword` | `store.keyword()` (FTS5 BM25) | Record `n_hits`. Zero hits is the signal that triggers `rarest_term`. |
| `collapse` | `store.units()` + group loop | Record `n_candidates`, `n_results`. |
| `enrich` | the `group_units()` loop at the end | **One SQL query per hit (N+1)**. Small at k=10, but it is the first thing to check if `/api/search?k=100` is slow. |

**Ask** (`answer.ask`), around the retrieval spans above:

| Span | Code | Attributes |
|---|---|---|
| `keywords` | `store.keyword(kw)` + `rarest_term()` | `fallback_used`. `rarest_term` runs one `keyword_count` per query word. |
| `pack` | `pack()` | `n_sources`, `chars`, `est_tokens` (chars/4), `n_truncated`, `n_dropped` |
| `pack.picture` | `load_picture()` per picture | PDF page renders can be slow (`--images`) |
| `generate` | `llm.stream()` / `complete()` | see below |
| `check` | `check()` + masking | `refused`, `confidence`, `n_unverified`. Expected to be negligible, which is why it is worth showing. |
| `attempt` | each pass of the `while True` loop | `attempt=2` marks the rarest-term retry, so a retried answer shows **two** retrieval + generation pairs, not one long mystery. |

**Generation** (`OpenAICompatLLM.stream`) is where most of the time goes, and it is the most useful part to split:

| Measure | How | What it tells you |
|---|---|---|
| `connect` → response headers | time until `client.stream()` returns | queueing and model **load** (cold start after `keep_alive: 2m` expires) |
| `first_chunk` | first SSE `data:` line | the runtime has started prefill |
| `ttft` (first **content** token) | first non-empty `delta.content` | what the user waits for. A large gap between `first_chunk` and `ttft` means the model is *thinking* (reasoning chunks have no `content`, which is the runaway case from P6). |
| `total` | `[DONE]` | — |
| `n_chunks`, `n_chars` | counted in the loop | — |
| `prompt_tokens`, `completion_tokens` | request `stream_options: {"include_usage": true}` and read the final usage-only chunk, which the loop currently skips | **Validates the chars/4 budget.** If real `prompt_tokens` exceeds `OLLAMA_CONTEXT_LENGTH`, the runtime may silently truncate the prompt. `ask.md` lists that as a risk, and nothing measures it today. |
| `decode_tok_s` | `completion_tokens / (total − ttft)` | compare runtimes and models |
| `hit_max_tokens` | `finish_reason == "length"` | settles the open `llm_max_tokens = 2048` risk in `ask.md` |

What each runtime reports beyond the OpenAI fields:

- **Ollama `/v1`** accepts `stream_options.include_usage` ([Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility.md)). Third-party traces suggest usage arrives in a final chunk with empty `choices` ([llama-stack trace](https://git.kvant.cloud/phoenix-oss/llama-stack-mirror/commit/ff94898b875fea6038c8a10c4bfcdf3c82e983b5)). Its detailed `load_duration` / `prompt_eval_duration` / `eval_duration` come only from the native `/api/chat`, not `/v1`. **Verify** the chunk layout against Ollama 0.40.x before relying on it.
- **llama.cpp `llama-server`** adds a `timings` object (`prompt_n`, `prompt_ms`, `predicted_n`, `predicted_ms`, `predicted_per_second`, `cache_n`) to the final chunk ([server-context.cpp](https://huggingface.co/OpenTransformer/llama.cpp-prismml/blob/main/tools/server/server-context.cpp), [server-bench.py](https://huggingface.co/datasets/echodict/llama.cpp/blob/main/scripts/server-bench.py)), and has a separate Prometheus `/metrics`. A recent build fixed how these were timed ([b7684 notes](https://newreleases.io/project/github/ggml-org/llama.cpp/release/b7684)).
- So: compute TTFT and wall time **client-side** for every runtime, and if the final chunk carries `usage` or `timings`, copy them in as-is under `runtime`. Don't branch on the runtime's name.

**Indexing** (later phase): per-file `extract`, `ocr`, `embed_text`, `embed_image`, `write`, summed per file type in the `run()` summary. This shows whether OCR or image embedding dominates a slow index.

## Design

### Recorder: explicit object, not a context variable

```python
class Trace:                                   # trace.py, sketch
    def __init__(self): self.root = {"name": "request", "ms": 0, "children": []}; self._stack = [self.root]; ...
    @contextmanager
    def span(self, name, **attrs): ...         # perf_counter in/out, appends a child dict, attrs are numbers/bools only
    def set(self, **attrs): ...                # attach counts to the current span
    def summary(self) -> dict: ...             # {"retrieval_ms", "generation_ms", "ttft_ms", "tok_s", ...}

NOOP = NullTrace()                             # default argument everywhere, so callers and tests don't change
```

Pass it as a parameter (`search(..., trace=NOOP)`, `ask(..., trace=NOOP)`), not through `contextvars`. `ask()` is a
generator, and in `serve` Starlette's `StreamingResponse` advances a sync generator from a thread pool, one `next()`
at a time in a copied context. A context variable set inside the generator therefore isn't reliably visible on the
next step. An explicit argument is also easier to follow, which suits a learning codebase.

**One caveat to document in the code.** `ask()` streams, so any span open across a `yield` (`generate`, `attempt`)
also counts the time the consumer takes to handle each delta: CLI printing, or the socket to the browser. That's
negligible locally, but it means "generation" is "time until the last token reached the consumer". The `runtime`
numbers, where available, are the server's own view.

### Surfaces

| Surface | Default | Opt-in |
|---|---|---|
| `labrador ask` | status line gains `· retrieval 0.21 s · answer 4.8 s · first token 1.2 s · 38 tok/s · 3,480 → 182 tokens` | `--trace`: indented per-stage span tree on **stderr** |
| `labrador ask --json` | `"timings": {retrieval_ms, answer_ms, ttft_ms, tok_s, prompt_tokens, completion_tokens}` | `--trace` adds `"trace": {…tree…}` |
| `labrador search` | `12 results in 0.18 s` on stderr | `--trace` |
| `POST /api/ask` | `sources` event carries `retrieval_ms` (shown while waiting). `done` carries `timings`. The page shows them under the status line. | — |
| `GET /api/search` | [`Server-Timing`](https://developer.mozilla.org/docs/Web/HTTP/Headers/Server-Timing) header (`embed;dur=41, dense;dur=3, keyword;dur=2, …`). It appears in the browser's Network → Timing panel with **no UI code**. | — |
| `labrador eval --answers` | per-row `timings` next to `seconds`, plus p50/p95 per stage in the summary | — |

`Server-Timing` doesn't suit the streamed `/api/ask`, because headers go out before the work is done and browsers
don't surface it in trailers. Use the event fields there. The header must not leak query text, which holds as long
as it carries only fixed span names. The existing CSP is unaffected.

### Privacy rules (fit with `docs/design/ask.md` non-goals)

- Attributes are numbers, booleans and fixed enums only: no question, keyword, term, path, snippet or answer text.
  Enforce it in `Trace.span` (reject `str` values except a fixed allow-list such as `mode="json"`) and test it.
- Nothing is written to disk. Even text-free, timing rows per question would be a usage log, and the design says
  there is none. Eval runs already write to `evals/out/`, which covers the regression use case.

## Options considered

| Option | Verdict |
|---|---|
| **Hand-rolled span tree** (above) | **Recommended.** ~50 lines, no dependency, readable, fits the "every stage visible" rule. |
| stdlib `logging` at DEBUG | Use alongside for one-off events (cache reload, retry), but flat log lines are hard to aggregate into a per-request breakdown. |
| **OpenTelemetry SDK** + local collector (Jaeger, Phoenix, Langfuse) | Not now. Adds several packages and an exporter that sends data over the network, which is the posture labrador avoids. The GenAI semantic conventions (`gen_ai.client.operation.time_to_first_chunk`, `gen_ai.server.time_to_first_token`, …) are still marked *Development* and moved to their own repository with no tagged release ([OTel GenAI metrics](https://opentelemetry.website.cncfstack.com/docs/specs/semconv/gen-ai/gen-ai-metrics/index.md), [Dash0 overview](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained), [status write-up](https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke)). Many LLM auto-instrumentations record prompts and completions by default. If wanted later, a ~30-line adapter can replay the `Trace` tree into OTel spans and borrow those metric names. |
| Prometheus `/metrics` on `serve` | Overkill for a single-user local tool. Useful only if `serve` becomes long-running and shared. |
| Profilers (`cProfile`, `py-spy`, `torch.profiler`) | Debugging tools, not observability. Document them in `docs/` for "a span is slow, now what?" (`py-spy record -- labrador search …`). |

## Proposed rollout (each ≤ ~400 lines, per CLAUDE.md)

| Phase | Scope | Est. lines |
|---|---|---|
| O1 | `trace.py`; spans in `search()`, `answer.ask()`, `llm.stream()/complete()` incl. `include_usage`; CLI status-line timings and `ask --json` `timings`; tests (span tree shape, NOOP default, no-strings rule, FakeLLM timings) | ~250 |
| O2 | Web: `retrieval_ms` on `sources`, `timings` on `done`, display in `app.js`; `Server-Timing` on `/api/search`; `test_web.py` | ~120 |
| O3 | `--trace` tree on stderr for `ask`/`search`; `eval --answers` per-stage p50/p95 | ~150 |
| O4 | *Deferred:* indexing per-stage timings in `indexer.run()` summary | ~100 |

The design doc, [docs/design/observability.md](../docs/design/observability.md), cites this report, owns the rollout table, and lists under
"Risks and open questions" the Ollama usage-chunk layout (to verify) and the consumer-time caveat on streamed spans.

## Decisions

1. **Default vs `--trace`.** Decided: the top-level metrics show by default. For ask that is retrieval time, answer
   time, time to first token, tokens/s and prompt/completion token counts
   (`retrieval 0.21 s · answer 4.8 s · first token 1.2 s · 38 tok/s · 3,480 → 182 tokens`); for search,
   `N results in 0.18 s`. Token counts and tokens/s come from the runtime's `usage` chunk. When a runtime doesn't send
   one, they are left out of the line rather than estimated. The per-stage breakdown (the span tree and its
   attributes: `matrix`, `embed_query`, `keyword`, `pack`, `lock_wait`, …) appears only with `--trace`. `ask --json`
   always carries the top-level metrics in `timings` and adds the tree under `trace` only with `--trace`. The web UI
   shows the same top-level metrics under the status line. `Server-Timing` on `/api/search` stays, since it only
   shows in devtools.
2. **Indexing (O4).** Decided: out of scope for now; search and ask only. Tracked as a separate issue.
3. **Persistent trace log.** Decided: no log, not even an opt-in `--trace-file`. Timings live only in the
   command's output, the web response and `eval` output in `evals/out/`. This keeps the "no question log" rule in
   `docs/design/ask.md` as it stands.
