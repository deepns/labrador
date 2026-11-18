# Changelog

Notable changes to labrador, newest first. Phases (P0–P7, D1–D4) are rows of the rollout table in
[docs/design/ask.md](docs/design/ask.md#rollout); numbers in parentheses are pull requests.

## Unreleased

- O1: `ask` prints a timings line to stderr (retrieval, answer, first token, tok/s, prompt → completion tokens)
  and `ask --json` gains `timings`; `search` prints `N results in X s` to stderr. Streaming requests now send
  `stream_options: {"include_usage": true}` so the runtime reports token counts. See
  [Reading the result](docs/usage/asking.md#reading-the-result) and [the design](docs/design/observability.md).
- LLM limits (#21): `ask`, Ask mode and `eval --answers` stop a generation after 300 s overall (`llm_deadline_s`,
  thinking included) and send `max_tokens: 2048` (`llm_max_tokens`), so a model that thinks without end no longer
  hangs them.
- P6: `ask --images` (also `eval --answers --images` and a "Read pictures" box in the web UI's Ask mode) attaches the
  original picture of the top image / PDF-page sources for a vision model; see
  [Reading pictures](docs/usage/asking.md#reading-pictures---images). Off by default: on the benchmark it gave no
  gain, made answers about 3× slower, and one run hung; see [the answers report](evals/answers/REPORT.md).
- D2 (#18): usage pages for [indexing](docs/usage/indexing.md), [searching](docs/usage/searching.md), the
  [web UI](docs/usage/web-ui.md) and [evaluating](docs/usage/evaluating.md); the README is cut down to a front door
  that links to them.
- D4: [CLI reference](docs/reference/cli.md) generated from the parser by `scripts/gen_cli_reference.py`, with a
  test that fails when it is stale; [configuration reference](docs/reference/configuration.md); this changelog.
- P5b (#19): `labrador eval --answers` scores `ask` over `bench/data/qa.jsonl` and takes the LLM flags; the
  [answer-quality report](evals/answers/REPORT.md); the default LLM is now `qwen3.5:4b` (was `gemma4:e4b`).
- Web UI (#16): Ask mode hides search results and drops searches still in flight when you switch modes.

## 0.1.0 (2026-11-15)

### Added

- **P4** (#15): `POST /api/ask` and an Ask mode in the web UI; `serve` takes the same LLM flags as `ask`.
- **P3** (#14): `labrador ask`, answering a question from your files with a local LLM, with masked IDs (`--reveal`
  to show them), `--json`, `--k` and the LLM flags; the [Asking questions](docs/usage/asking.md) page and a local
  answers section in installation.
- **P2b** (#11): `answer.py`, the ask pipeline: retrieve, pack sources, generate, check citations, mask, all tested
  on a fake LLM.
- **P2a** (#5): `llm.py`, a client for OpenAI-compatible runtimes that refuses non-loopback URLs unless allowed;
  LLM settings; `httpx` becomes a main dependency.
- **P5a** (#10): fictional identity documents in `bench/make_bench.py` and `bench/data/qa.jsonl` for the answer
  benchmark.
- **D3** (#13): [FAQ](docs/faq.md), [Security and privacy](docs/security-privacy.md) and a root `SECURITY.md`.
- **D1** (#9): the docs front page, installation and quick start pages; `cli.build_parser()`; `tests/test_docs.py`
  checking links, documented flags and the quick start.
- The design doc for local LLM answers (#2) and research notes (#1).
- CI on macOS, a PR template, the PR size guideline and the implementer agent (#3); pre-commit with ruff and a
  check for machine-specific paths.

### Changed

- **P0** (#1): keyword search (BM25) drops filler words from the query.

### Security

- **P1** (#4): index directories `0700` and files `0600`; the web UI checks Host and Origin, sends a CSP and
  `Cache-Control: no-store`, and binds to loopback unless `--allow-lan`.

### Initial

- Local multimodal search over text, DOCX, PDF and images with EmbeddingGemma 2: SQLite vectors plus FTS5, fused
  with per-modality z-scores and RRF; `index`, `search`, `serve`, `watch`, `stats` and `eval`.
