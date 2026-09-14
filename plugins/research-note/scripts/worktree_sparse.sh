#!/usr/bin/env bash
# worktree_sparse.sh — make every linked worktree of this project SPARSE:
# no project_memory/, no wiki/. The cluster clone's exclusion, applied at
# home, for the same reason ("a stale record copy is a page someone
# eventually reads and believes") plus one more: read-first from inside a
# worktree physically cannot hit a branch-point snapshot when the snapshot
# is not there. Record writes never needed the copy anyway — the bus places
# a scratch copy onto main from any cwd.
#
# Wired on PostToolUse(EnterWorktree) for Claude and SessionStart for Codex.
# With `--current PATH`, it handles that one verified linked worktree wherever
# Codex created it. Without the flag it retains the legacy sweep over
# .claude/worktrees/. Failures are silent by design (an
# old git without per-worktree sparse support leaves a FULL worktree, which
# every mechanism already tolerates); the one loud case is MAIN losing its
# record, which must never happen and aborts red.
set -uo pipefail
PROJ="${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[ -f "$PROJ/.claude/framework.json" ] || exit 0
MAIN="$(dirname "$(git -C "$PROJ" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" || exit 0
[ -d "$MAIN/project_memory" ] || exit 0

make_sparse() {
    w=$1
    [ "$w" = "$MAIN" ] && return 0
    git -C "$w" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    git -C "$w" sparse-checkout set --no-cone '/*' '!/project_memory/' '!/wiki/' 2>/dev/null || return 0
}

if [ "${1:-}" = "--current" ]; then
    current=${2:-$PWD}
    current=$(cd "$current" 2>/dev/null && pwd -P) || exit 0
    listed=0
    while IFS=' ' read -r key val; do
        [ "$key" = worktree ] || continue
        [ "$val" = "$current" ] && listed=1
    done <<EOF
$(git -C "$MAIN" worktree list --porcelain 2>/dev/null)
EOF
    [ "$listed" -eq 1 ] && make_sparse "$current"
else
git -C "$MAIN" worktree list --porcelain 2>/dev/null | while IFS=' ' read -r key val; do
    [ "$key" = worktree ] || continue
    w=$val
    [ "$w" = "$MAIN" ] && continue
    case "$w" in */.claude/worktrees/*) ;; *) continue ;; esac
    make_sparse "$w"
done
fi
[ -d "$MAIN/project_memory" ] || { echo "worktree_sparse: MAIN lost project_memory/ — investigate NOW" >&2; exit 1; }
exit 0
