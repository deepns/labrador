#!/bin/sh
# PostToolUse (Write|Edit): lint-fix the edited Python file; report what ruff can't fix.
f=$(jq -r '.tool_input.file_path // empty')
case "$f" in *.py) ;; *) exit 0 ;; esac
[ -f "$f" ] || exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
out=$(uv run --extra dev ruff check --fix --quiet "$f" 2>&1) || { echo "$out" >&2; exit 2; }
