#!/bin/sh
# PreToolUse (Bash): before `gh pr create`, ask for a docs check if the branch changes code under labrador/.
# Passes once /docs-audit has run (it leaves a marker); otherwise blocks once, then lets a retry through.
in=$(cat)
cmd=$(printf '%s' "$in" | jq -r '.tool_input.command // empty')
printf '%s' "$cmd" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+create' || exit 0
dir=$(printf '%s' "$in" | jq -r '.cwd // empty')
cd "${dir:-$CLAUDE_PROJECT_DIR}" 2>/dev/null || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
[ -n "$(git diff --name-only origin/main...HEAD -- labrador 2>/dev/null)" ] || exit 0
marker="$(git rev-parse --git-common-dir)/docs-audit-$(printf '%s' "$branch" | tr '/' '-')"
[ -e "$marker" ] && exit 0
touch "$marker"
echo "This branch changes labrador/ but /docs-audit hasn't run on it. Run /docs-audit and fold its fixes into" \
     "the PR, or say why the docs are unaffected; then run gh pr create again." >&2
exit 2
