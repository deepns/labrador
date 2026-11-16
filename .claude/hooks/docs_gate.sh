#!/bin/sh
# PreToolUse (Bash): before `gh pr create`, or `git push` to a branch with an open PR, ask for a docs check if
# the branch changes code under labrador/. The marker holds the HEAD sha that /docs-audit last covered; if HEAD
# differs, block once (recording HEAD), then let a retry through.
in=$(cat)
cmd=$(printf '%s' "$in" | jq -r '.tool_input.command // empty')
if printf '%s' "$cmd" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+create'; then kind=create
elif printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push'; then kind=push
else exit 0; fi
dir=$(printf '%s' "$in" | jq -r '.cwd // empty')
cd "${dir:-$CLAUDE_PROJECT_DIR}" 2>/dev/null || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
head=$(git rev-parse HEAD 2>/dev/null) || exit 0
[ -n "$(git diff --name-only origin/main...HEAD -- labrador 2>/dev/null)" ] || exit 0
# A push only needs the audit when it updates an open PR (fail open if gh is missing or errors).
[ "$kind" = create ] || [ "$(gh pr view --json state -q .state 2>/dev/null)" = OPEN ] || exit 0
marker="$(git rev-parse --git-common-dir)/docs-audit-$(printf '%s' "$branch" | tr '/' '-')"
[ "$(cat "$marker" 2>/dev/null)" = "$head" ] && exit 0
printf '%s\n' "$head" > "$marker"
if [ "$kind" = create ]; then
  echo "This branch changes labrador/ but /docs-audit hasn't run on it. Run /docs-audit and fold its fixes into" \
       "the PR, or say why the docs are unaffected; then run gh pr create again." >&2
else
  echo "This push adds commits to an open PR that changes labrador/, and /docs-audit hasn't run on HEAD. Run" \
       "/docs-audit and fold its fixes in, or say why the docs are unaffected; then push again." >&2
fi
exit 2
