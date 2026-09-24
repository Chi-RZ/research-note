#!/usr/bin/env bash
# worktree_retire.sh — remove a linked worktree, but not while someone is in it.
#
# Usage:
#   worktree_retire.sh <worktree-path> [--force]
#
# THE INCIDENT THIS EXISTS FOR
#
# A worktree was removed after its branch had landed, while the agent working in
# it was still running. Nothing failed. The agent's paths resolved to the main
# checkout instead, and it went on committing there — to main, directly, for the
# rest of its run. It was found afterwards, by reading history.
#
# That is the worst shape a failure can take here: no error, no refusal, and the
# damage lands in the one place the project treats as authoritative. `git
# worktree remove` cannot catch it, because from git's side removing a worktree
# whose branch has merged is exactly the right thing to do. What git does not
# know is that a process is still living in that directory.
#
# So the check is about processes, not about git: refuse while any process has
# its working directory inside the worktree. On Linux that is /proc/<pid>/cwd;
# elsewhere lsof answers the same question. Where neither is available the
# script says so and refuses rather than guessing — a silent removal is the
# thing being prevented.
#
# LIMIT, STATED PLAINLY: this only helps if it is what gets called. Nothing
# stops `git worktree remove`, and the framework does not wrap it. Treat this as
# the safe spelling to reach for, not as a guard the machine enforces.
set -euo pipefail

WT="${1:?usage: worktree_retire.sh <worktree-path> [--force]}"
FORCE=0; [ "${2:-}" = "--force" ] && FORCE=1

[ -d "$WT" ] || { echo "worktree_retire: $WT does not exist" >&2; exit 2; }
WT="$(cd "$WT" && pwd -P)"

MAIN="$(dirname "$(git -C "$WT" rev-parse --path-format=absolute --git-common-dir)")"
[ "$WT" != "$MAIN" ] || {
    echo "worktree_retire: $WT is the MAIN checkout, not a linked worktree" >&2; exit 2; }

# Who is living in there?
occupants() {
    if [ -r /proc/self/cwd ]; then
        # One process for the whole scan: a readlink and a subshell per pid
        # cost ~9 s on a box running 2000 processes.
        python3 - "$WT" <<'PY'
import os, sys
wt = sys.argv[1]
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        continue
    if cwd == wt or cwd.startswith(wt + "/"):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            cmd = ""
        print(pid, cmd[:70])
PY
    elif command -v lsof >/dev/null 2>&1; then
        lsof -a -d cwd -F pcn +D "$WT" 2>/dev/null \
            | awk '/^p/{pid=substr($0,2)} /^c/{print pid, substr($0,2)}' | sort -u
    else
        echo "UNKNOWN"
    fi
}

OCC="$(occupants || true)"

if [ "$OCC" = "UNKNOWN" ]; then
    [ "$FORCE" = 1 ] || {
        echo "worktree_retire: cannot tell whether anything is running in $WT" >&2
        echo "  (no /proc and no lsof). Refusing rather than guessing — --force to override." >&2
        exit 1; }
elif [ -n "$OCC" ]; then
    [ "$FORCE" = 1 ] || {
        echo "worktree_retire: $WT is still someone's working directory:" >&2
        printf '  %s\n' "$OCC" >&2
        echo "  Removing it now would not stop them — their paths would resolve to" >&2
        echo "  $MAIN and they would keep committing there. Wait, or --force." >&2
        exit 1; }
    echo "worktree_retire: --force over $(printf '%s\n' "$OCC" | wc -l) live occupant(s)" >&2
fi

BRANCH="$(git -C "$WT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
# `${FORCE:+...}` would always fire — FORCE is 0 or 1 and both are non-empty.
if [ "$FORCE" = 1 ]; then git -C "$MAIN" worktree remove --force "$WT"
else                      git -C "$MAIN" worktree remove "$WT"; fi
echo "worktree_retire: removed $WT${BRANCH:+ (was on $BRANCH)}"
echo "  the branch itself is untouched — delete it separately once you are sure it landed"
