#!/bin/sh
# pre-commit hook: block machine-specific paths and links to gitignored eval output.
# Checks only lines being added, so existing text never trips it.
pattern='/Users/[A-Za-z]|(^|[[:space:]"=(])/home/[a-z]|~/Downloads|~/Desktop|indexes/[A-Za-z0-9_.-]+-[0-9a-f]{10}|evals/deep/(results|analysis)-'
hits=$(git diff --cached -U0 --diff-filter=ACM -- "$@" | grep -E '^\+[^+]' | grep -nE "$pattern")
if [ -n "$hits" ]; then
  echo "Local paths in staged changes:" >&2
  echo "$hits" >&2
  echo "Use the repo conventions (bench/data/, evals/out/), or commit with --no-verify if intended." >&2
  exit 1
fi
