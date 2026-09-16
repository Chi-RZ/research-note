#!/usr/bin/env bash
# land_and_launch.sh — rebase a worktree branch onto main, fast-forward main to
# it, and launch from main, as ONE transaction against main's WORKING TREE.
#
# Usage (from the worktree, or from main with --branch):
#   land_and_launch.sh -- <launch command> [args...]
#   land_and_launch.sh --branch <name> -- <launch command> [args...]
#   land_and_launch.sh --land-only          # rebase + ff-merge, no launch
#
# WHY A LOCK, AND WHY OVER ALL THREE STEPS
#
# Two agents each rebasing onto main and ff-merging need no coordinator: git is
# the coordination. A rebase reads main's ref, and if the other agent landed
# first the merge fails as "not a fast-forward" and the loser rebases again —
# an ordinary compare-and-swap retry.
#
# What is NOT safe is main's WORKING TREE, and that is what this protects.
# `git merge` rewrites files there; launch_bare_gpu.sh reads that same working
# tree to build its log header — the repo SHA and the `# --- dirty diff ---`
# block, via `git status --porcelain`. A merge landing between the launcher's
# read and its write records a transient state in the header, and that header
# is the only thing tying a recorded result to the code that produced it. The
# failure is silent, it is in the record rather than in git, and no later check
# can detect it: the header looks well-formed and names a tree that never ran.
#
# So the lock spans rebase -> merge -> launch. Locking only the merge would be
# equivalent to not locking at all, since the launcher's read is the other half
# of the race. Holding the rebase inside it also removes the retry: main cannot
# move between the rebase that reads it and the merge that writes it, so
# `merge --ff-only` cannot fail for a reason a retry would fix.
#
# Modelled on record_sync.sh, which holds this shape for project_memory/:
# resolve main through --git-common-dir (shared by every worktree, so it is
# found from anywhere), hold the lock on an inherited file descriptor so it
# lasts the rest of the script, and take it with fcntl.flock from python3 —
# macOS ships no flock(1).
#
# A SEPARATE lock file from record.lock on purpose: landing code and writing
# the record are unrelated, and one lock would make them block each other for
# nothing.
set -euo pipefail

BRANCH=""; LAND_ONLY=0; declare -a CMD=()
while [ $# -gt 0 ]; do
    case "$1" in
        --branch) BRANCH="${2:?--branch wants a name}"; shift 2 ;;
        --land-only) LAND_ONLY=1; shift ;;
        --) shift; CMD=("$@"); break ;;
        *) echo "land_and_launch: unknown argument $1" >&2; exit 2 ;;
    esac
done
[ "$LAND_ONLY" = 1 ] || [ ${#CMD[@]} -gt 0 ] || {
    echo 'land_and_launch: nothing to launch — pass "-- <command>" or --land-only' >&2
    exit 2
}

HERE="$(pwd)"
git -C "$HERE" rev-parse --git-dir >/dev/null 2>&1 || {
    echo "land_and_launch: not a git repository" >&2; exit 2; }

# The main checkout, from anywhere: --git-common-dir is shared by every linked
# worktree, so this resolves to main whether we run in one or not.
MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
[ -d "$MAIN" ] || { echo "land_and_launch: cannot resolve the main checkout" >&2; exit 2; }

[ -n "$BRANCH" ] || BRANCH="$(git -C "$HERE" rev-parse --abbrev-ref HEAD)"
DEFAULT="$(git -C "$MAIN" rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" != "$DEFAULT" ] || {
    echo "land_and_launch: $BRANCH is what main is on — nothing to land" >&2; exit 2; }

# The branch's own worktree: where the rebase runs. It is this directory when
# called from the worktree; otherwise ask git which worktree holds the branch.
WT="$HERE"
if [ "$(git -C "$HERE" rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
    WT="$(git -C "$MAIN" worktree list --porcelain \
          | awk -v b="refs/heads/$BRANCH" '/^worktree /{w=$2} /^branch /{if($2==b){print w; exit}}')"
    [ -n "$WT" ] || { echo "land_and_launch: no worktree holds $BRANCH" >&2; exit 2; }
fi

# Refuse a dirty branch BEFORE taking the lock: a rebase would fail anyway, and
# failing early keeps the lock free for whoever is ready.
[ -z "$(git -C "$WT" status --porcelain)" ] || {
    echo "land_and_launch: $WT has uncommitted changes — commit them first" >&2; exit 2; }

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib_state.sh"
STATE="$(rn_state_dir "$MAIN")" || { echo "land_and_launch: cannot create $MAIN/.research-note/state" >&2; exit 2; }
exec 9>"$STATE/land.lock"

# 180 s. The launch itself is fast — launch_bare_gpu.sh backgrounds the job and
# returns after a 3 s PID probe, it does not wait for the run. What varies is
# the rebase, and a rebase long enough to exhaust this is one that needs a human
# anyway. record_sync.sh uses 60 s for a copy-and-lint; this budget is three
# times that because it also merges and starts a process.
python3 -c 'import fcntl, signal, sys
signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
signal.alarm(180)
fcntl.flock(9, fcntl.LOCK_EX)' \
    || { echo "land_and_launch: land.lock still held after 180s — is another agent landing?" >&2
         exit 1; }

# From here to the end of the script the lock is held on fd 9, released when
# this process exits however it exits.

BASE="$(git -C "$MAIN" rev-parse HEAD)"
echo "land_and_launch: landing $BRANCH onto $DEFAULT ($(git -C "$MAIN" rev-parse --short HEAD))"

# Rebase INSIDE the lock, so main cannot move before the merge reads it.
# A conflict must not leave the repository mid-rebase while we hold the lock:
# abort, release, and let a human resolve it in the worktree.
if ! git -C "$WT" rebase "$BASE" >/dev/null 2>&1; then
    git -C "$WT" rebase --abort >/dev/null 2>&1 || true
    echo "land_and_launch: $BRANCH does not rebase cleanly onto $DEFAULT — rebase aborted," >&2
    echo "  the worktree is unchanged. Resolve it there, then run this again." >&2
    exit 1
fi

git -C "$MAIN" merge --ff-only "$BRANCH" >/dev/null || {
    echo "land_and_launch: ff-merge of $BRANCH failed after a clean rebase — main moved" >&2
    echo "  under the lock, which should be impossible. Investigate before retrying." >&2
    exit 1; }
echo "land_and_launch: $DEFAULT is now $(git -C "$MAIN" rev-parse --short HEAD)"

[ "$LAND_ONLY" = 0 ] || exit 0

# Launch FROM MAIN. launch_bare_gpu.sh refuses to run in a linked worktree —
# correctly, since a worktree's logs die with it and leave a dangling link on a
# page that outlives it — so the launch has to happen here, after the landing,
# which is the whole reason these two steps share a transaction.
cd "$MAIN"

# `9>&-` closes the lock fd FOR THE CHILD ONLY. It matters because
# launch_bare_gpu.sh backgrounds the run and returns in about three seconds:
# without this the backgrounded job inherits fd 9 and holds the lock for its
# whole lifetime — hours — blocking every other agent from landing. This script
# keeps the lock itself, so the window that needs protecting (the launcher
# reading main's working tree to build its header) is still covered, and it is
# released when this process exits a moment later.
"${CMD[@]}" 9>&-
