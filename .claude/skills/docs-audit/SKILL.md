---
name: docs-audit
description: Check labrador's docs against the code with the docs-keeper agent and fix the drift. Use before opening a PR or pushing new commits to an open PR (default, checks the branch diff), when the docs_gate hook blocks `gh pr create` or `git push`, or with `full` for a whole-repo sweep.
---

# docs-audit

`/docs-audit` checks the current branch's diff against `origin/main`. `/docs-audit full` checks every doc.
`/docs-audit <ref>` uses another base.

1. **Run the agent.** Dispatch the `docs-keeper` subagent with the scope (`diff` or `full`) and base ref. It is
   read-only and returns a findings table.
2. **Decide each finding.** For each row, check the cited code yourself before acting: the agent can be wrong.
   - The doc is wrong: apply the proposed fix (doc edits may be made in the main session).
   - The code is wrong: don't touch the doc; tell the user, since that is a code change for `implementer`.
   - Not a real problem: drop it and say why in one line.
3. **Where the fixes go.**
   - `diff` scope: on the current branch, in the same PR as the code. Anything left open goes under "Notes for the
     reviewer" in the PR body.
   - `full` scope: on a new `docs/<topic>` branch off `origin/main`, as a docs-only PR. Keep it within ~400 changed
     lines; split by doc if it grows.
4. **Record it.** Tick the docs line of the PR template with the outcome: no drift, fixed in this PR, or listed
   for the reviewer. Commit any fixes, then record the audit with
   `git rev-parse HEAD > "$(git rev-parse --git-common-dir)/docs-audit-<branch>"` (branch name with `/` replaced
   by `-`). The `docs_gate` hook checks that sha before `gh pr create` and before `git push` to an open PR.

Never let the agent's output stand in for checking: a "No drift found" result still lists the docs it checked, so
confirm the ones the diff should have touched are on that list.
