# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

labrador is a learning-sized (~1,200 lines) local multimodal search tool built on EmbeddingGemma 2. Keep every pipeline stage visible in plain, readable code; the README's diagram and command table are the user-facing reference.

## Pipeline

`extractors` → *units* → `embedder` → `store` (SQLite: vectors + FTS5) ← `search` ← `cli` / `web`. Each module's docstring explains its stage; read it before changing that stage.

## Git

- **Never commit to `main`.** Create a branch, commit there, and open a PR against `main`. The `no-commit-to-branch` pre-commit hook rejects commits on `main`.
- **Keep PRs human-reviewable**: aim for ≤ ~400 changed lines (excluding `uv.lock`) and one concern per PR. Split big work by phase or module, or land a refactor before the feature that needs it; never one PR with thousands of lines of diff. CI's `pr-size` job warns above 400.
- **Models**: design and review run on Opus 5.5 in the main session; all code writing goes to the `implementer` subagent (`.claude/agents/implementer.md`, Sonnet 5.5) with a scoped brief, and the main session reviews its diff before committing.
- **CI** (`.github/workflows/ci.yml`) runs pre-commit on all files and `pytest` on macOS for every PR; fill in `.github/pull_request_template.md`.

## Testing

- **Plumbing** changes: `uv run --extra dev pytest -q` (single test: append `tests/test_pipeline.py::<name>`). Tests and `--backend fake` use a hashing embedder, so they need no model download. The OCR test is skipped without an OCR backend: on a Mac add `--extra mac`, and never `uv sync` with fewer extras than you use, since sync uninstalls the rest.
- **Ranking-quality** changes: the fake embedder says nothing about quality. Index the benchmark with the real model and compare `labrador eval bench/data/queries.jsonl --out <file>.json` before and after. Run `uv run python scripts/check_model.py` first on a new machine or after touching `embedder.py`.
- **Web UI** changes (`web.py`, `static/`, headers): `tests/test_web.py` checks responses, not rendering. Run `labrador serve` on `~/labrador-sample`, click through search, filters, lightbox, Open and Show in Finder in a browser with the console open (CSP violations only show there), and attach before/after screenshots to the PR.
- **Eval output** (`--out` files, harness results, analysis dumps) goes in `evals/out/`, which is gitignored. Commit the harness scripts and the written-up `REPORT.md`, never the raw results.
- **Reports**: research that a design doc cites goes in `reports/` as Markdown. Generated reports, status snapshots and PR review notes go in `reports/local/`, which is gitignored; reviews belong on the PR itself.
- **No machine-specific paths** in committed files: no `/Users/<name>`, `~/Downloads`, real index folder names (a folder name plus its 10-hex hash) or links to gitignored output. Use the documented conventions (`bench/data/`, `~/labrador-sample`, `~/.labrador/indexes/<folder>-<hash>`, `evals/out/`).

## Invariants

- **Units and groups.** One unit = one vector; units sharing a `group` collapse into one result. New file types emit units through `extract()` / `file_type()` and extend the extension sets in `config.py`.
- **dtype**: float32 (default) or bfloat16 only. The model emits NaNs in float16.
- **Read-only source folder.** All writes go to the index dir, `~/.labrador/indexes/<folder>-<sha1[:10]>/` (root overridable with `LABRADOR_HOME`).
- **Embedder fingerprint** is `Embedder.fingerprint()` = `name:dim`, stored in `meta.embedder`. `Store.check_model` refuses a mismatched index, and `cli._open` infers backend and dim from it. It covers only model and dim: after changing document formatting, vision token budgets or dtype, re-index with `--rebuild` so old and new vectors never share an index.
- **Modality gap.** Text→image cosines run lower than text→text, so search z-scores each modality separately before fusing with BM25 via RRF. Compare scores within a modality, never raw cosines across modalities.
