## What and why

<!-- One or two sentences: what changes, and why. Link the design doc or rollout phase if there is one. -->

## Kind of change

- [ ] Plumbing (behaviour unchanged for ranking; `pytest` is enough)
- [ ] Ranking or answer quality (eval before/after below)
- [ ] Web UI (`web.py`, `static/`, response headers; manual check below)
- [ ] Docs only

## Checklist

- [ ] **Reviewable size**: ≤ ~400 changed lines (excluding `uv.lock`), one concern per PR. If larger, say why below or split it.
- [ ] `uv run --extra dev pytest -q` passes
- [ ] Ranking changes: `labrador eval bench/data/queries.jsonl --out evals/out/<name>.json` before and after, numbers below
- [ ] Invariants in CLAUDE.md still hold (units/groups, dtype, read-only source folder, embedder fingerprint, per-modality z-scores)
- [ ] Re-index needed? If document formatting, vision budgets or dtype changed, say so: `labrador index --rebuild`
- [ ] User-facing docs updated in this PR (README / `docs/`), and the rollout table in `docs/design/` if this is a planned phase
- [ ] No machine-specific paths or links to gitignored output

## Eval (ranking or quality changes only)

| | hit@1 | hit@5 | MRR@10 |
|---|---|---|---|
| before | | | |
| after | | | |

## UI check (web UI changes only)

<!-- Run `labrador serve` on `~/labrador-sample` (`--backend fake` is fine) and check in a real browser. The author checks; the reviewer only re-checks. -->

- [ ] Screenshots: before (`main`) and after for each screen touched, or one after-shot if nothing should look different
- [ ] Browser console clean on load, search, filters and lightbox (no errors, no CSP violations)
- [ ] Flows still work: search, filter chips, lightbox, Open (PDFs at the right page), Show in Finder
- [ ] Browsers checked: <!-- e.g. Safari 18, Chrome 131 -->

## Notes for the reviewer

<!-- Where to start reading, anything deliberately left out, follow-ups. -->
