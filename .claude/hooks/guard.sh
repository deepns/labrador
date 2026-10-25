#!/bin/sh
# PreToolUse (Bash|Write|Edit): block force-pushes to main and edits inside the index store.
in=$(cat)
cmd=$(printf '%s' "$in" | jq -r '.tool_input.command // empty')
if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push' \
   && printf '%s' "$cmd" | grep -Eq '(^|[[:space:]])(-f|--force|--force-with-lease)([[:space:]=]|$)|[[:space:]]\+main' \
   && printf '%s' "$cmd" | grep -Eq '(^|[[:space:]:+])main([[:space:]]|$)'; then
  echo "Blocked: force-push to main. Push a branch instead." >&2; exit 2
fi
f=$(printf '%s' "$in" | jq -r '.tool_input.file_path // empty')
store="${LABRADOR_HOME:-$HOME/.labrador}"
case "$f" in "$store"/*)
  echo "Blocked: $f is in labrador's index store. Rebuild with 'labrador index --rebuild' instead of editing it." >&2; exit 2 ;;
esac
exit 0
