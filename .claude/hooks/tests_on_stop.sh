#!/bin/sh
# Stop: if pipeline code or tests changed since HEAD, run the fast test suite.
# A failure blocks the stop once (stop_hook_active prevents a loop).
[ "$(jq -r '.stop_hook_active // false')" = "true" ] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -z "$(git status --porcelain -- labrador tests)" ] && exit 0
out=$(uv run --extra dev pytest -q 2>&1) || { echo "pytest failed after changes to labrador/ or tests/:" >&2; echo "$out" | tail -25 >&2; exit 2; }
