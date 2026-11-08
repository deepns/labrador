## What and why

<!-- One or two sentences: what changes, and why. Link the design doc or rollout phase if there is one. -->

## Kind of change

- [ ] Plumbing (behaviour unchanged for ranking; `pytest` is enough)
- [ ] Ranking or answer quality (eval before/after below)
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

## Notes for the reviewer

<!-- Where to start reading, anything deliberately left out, follow-ups. -->
