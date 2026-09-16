#!/usr/bin/env bash
# test_land_and_launch.sh — the landing transaction, against real repositories.
#
# Shell rather than pytest because every property here is about git worktrees,
# file descriptors and flock(2) — the things a mock would have to fake are
# exactly the things that can be wrong.
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/land_and_launch.sh"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }

# A project with main plus one linked worktree on its own branch.
fixture() {
    local root; root="$(mktemp -d)"
    git -C "$root" init -q -b main
    git -C "$root" config user.email t@example.com
    git -C "$root" config user.name t
    echo base > "$root/f"; git -C "$root" add f
    git -C "$root" commit -qm base
    git -C "$root" worktree add -q -b feat "$root/wt"
    echo "$root"
}

echo "land_and_launch:"

# --- the landing itself -----------------------------------------------------
R="$(fixture)"; WT="$R/wt"
echo work > "$WT/g"; git -C "$WT" add g; git -C "$WT" commit -qm work
( cd "$WT" && bash "$SCRIPT" --land-only ) >/dev/null 2>&1
check "ff-merges the branch into main" \
      "$(git -C "$R" log --oneline -1 --format=%s)" "work"
check "main's working tree has the landed file" "$(cat "$R/g" 2>/dev/null)" "work"
rm -rf "$R"

# --- the lock is real -------------------------------------------------------
R="$(fixture)"; WT="$R/wt"
echo work > "$WT/g"; git -C "$WT" add g; git -C "$WT" commit -qm work
mkdir -p "$R/.research-note/state"
# Hold land.lock from another process for 3 s. The right behaviour is to WAIT
# and then land — not to fail — so the property is elapsed time, not exit code.
# Asserting failure here would only test that the timeout is shorter than the
# hold, which is a property of the test rather than of the script.
python3 - "$R/.research-note/state/land.lock" <<'HOLD' &
import fcntl, sys, time
f = open(sys.argv[1], "w"); fcntl.flock(f, fcntl.LOCK_EX); time.sleep(3)
HOLD
HOLDER=$!; sleep 0.5
T0=$(date +%s)
( cd "$WT" && bash "$SCRIPT" --land-only ) >/dev/null 2>&1
LANDED=$?; ELAPSED=$(( $(date +%s) - T0 ))
wait $HOLDER 2>/dev/null
check "lands once the other holder releases" "$LANDED" "0"
[ "$ELAPSED" -ge 2 ] && ok "waited for land.lock rather than racing past it (${ELAPSED}s)" \
                     || bad "waited for land.lock rather than racing past it (${ELAPSED}s)"
rm -rf "$R"

# --- THE REGRESSION THAT MATTERS -------------------------------------------
# A launcher that backgrounds its job must not pass the lock to that job. If it
# does, the lock is held for the job's whole lifetime — hours — and every other
# agent blocks. `9>&-` on the child is what prevents it; an `exec` here would
# reintroduce it silently.
R="$(fixture)"; WT="$R/wt"
echo work > "$WT/g"; git -C "$WT" add g; git -C "$WT" commit -qm work
cat > "$R/fake_launcher.sh" <<'EOF'
#!/usr/bin/env bash
sleep 30 &          # stands in for the backgrounded run
echo $! > bg.pid
EOF
chmod +x "$R/fake_launcher.sh"
( cd "$WT" && bash "$SCRIPT" -- "$R/fake_launcher.sh" ) >/dev/null 2>&1
BG="$(cat "$R/bg.pid" 2>/dev/null)"
# the script has exited; if the lock is free the backgrounded child did not keep it
python3 - "$R/.research-note/state/land.lock" <<'PY'
import fcntl, sys
f = open(sys.argv[1], "w")
try:
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); sys.exit(0)
except BlockingIOError:
    sys.exit(1)
PY
[ $? -eq 0 ] && ok "the backgrounded job does not inherit the lock" \
             || bad "the backgrounded job does not inherit the lock"
kill "$BG" 2>/dev/null
rm -rf "$R"

# --- refusals ---------------------------------------------------------------
R="$(fixture)"; WT="$R/wt"
echo dirty > "$WT/g"                       # uncommitted
( cd "$WT" && bash "$SCRIPT" --land-only ) >/dev/null 2>&1
check "refuses a dirty branch" "$?" "2"
python3 - "$R/.research-note/state/land.lock" <<'PY' 2>/dev/null
import fcntl, sys, os
sys.exit(0 if not os.path.exists(sys.argv[1]) else 1)
PY
[ $? -eq 0 ] && ok "does not even create the lock when refusing early" \
             || bad "does not even create the lock when refusing early"
rm -rf "$R"

R="$(fixture)"
( cd "$R" && bash "$SCRIPT" --land-only ) >/dev/null 2>&1
check "refuses to land main onto itself" "$?" "2"
rm -rf "$R"

# --- a conflicting branch leaves the worktree clean -------------------------
R="$(fixture)"; WT="$R/wt"
echo theirs > "$R/f"; git -C "$R" commit -qam theirs
echo ours   > "$WT/f"; git -C "$WT" commit -qam ours
( cd "$WT" && bash "$SCRIPT" --land-only ) >/dev/null 2>&1
check "refuses a branch that does not rebase cleanly" "$?" "1"
check "aborts the rebase rather than leaving the worktree mid-rebase" \
      "$(git -C "$WT" rev-parse --abbrev-ref HEAD)" "feat"
rm -rf "$R"


echo "worktree_retire:"
RETIRE="$(dirname "$SCRIPT")/worktree_retire.sh"

R="$(fixture)"; WT="$R/wt"
# nobody in it -> removes
bash "$RETIRE" "$WT" >/dev/null 2>&1
check "removes an unoccupied worktree" "$([ -d "$WT" ] && echo yes || echo no)" "no"
rm -rf "$R"

R="$(fixture)"; WT="$R/wt"
# a process living in it -> refuses, and the worktree survives
( cd "$WT" && sleep 20 ) & OCCUPANT=$!
sleep 0.5
bash "$RETIRE" "$WT" >/dev/null 2>&1
check "refuses while a process has its cwd inside" "$?" "1"
check "and the worktree is still there" "$([ -d "$WT" ] && echo yes || echo no)" "yes"
kill $OCCUPANT 2>/dev/null; wait $OCCUPANT 2>/dev/null
rm -rf "$R"

R="$(fixture)"
bash "$RETIRE" "$R" >/dev/null 2>&1
check "refuses to retire the main checkout" "$?" "2"
rm -rf "$R"

echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
