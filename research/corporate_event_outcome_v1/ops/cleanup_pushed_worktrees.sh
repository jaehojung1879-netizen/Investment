#!/usr/bin/env bash
# Remove a dated LIVE-writer worktree ONLY when everything it committed is already on origin/signal-history
# and it holds no uncommitted change. Anything else (push failure, unsent receipt) is kept and reported.
# Usage: cleanup_pushed_worktrees.sh <repo> [glob-of-worktrees]
set -u
REPO="$1"; PATTERN="${2:-/tmp/kr-event-live-work-*/signal-history}"
git -C "$REPO" fetch -q origin signal-history || { echo "KEEP_ALL fetch-failed"; exit 0; }
for W in $PATTERN; do
  [ -d "$W" ] || continue
  if [ -n "$(git -C "$W" status --porcelain 2>/dev/null)" ]; then echo "KEEP $W uncommitted-change"; continue; fi
  if git -C "$REPO" merge-base --is-ancestor "$(git -C "$W" rev-parse HEAD)" FETCH_HEAD; then
    git -C "$REPO" worktree remove --force "$W" && rm -rf "$(dirname "$W")" && echo "REMOVED $W"
  else
    echo "KEEP $W unpushed-commit $(git -C "$W" rev-parse --short HEAD)"
  fi
done
git -C "$REPO" worktree prune
