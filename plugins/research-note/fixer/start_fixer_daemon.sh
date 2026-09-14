#!/usr/bin/env bash
# Start (or ensure running) the page-fixer DAEMON for one project.
# Usage: start_fixer_daemon.sh [PROJECT_DIR]   (SessionStart hook passes it)
#
# For hosts where a crontab is unavailable or unwanted: a self-supervising
# background loop replaces the cron entry — it re-invokes run_fixer.sh every
# 10 min, detached from any session (setsid), for as long as the host lives.
# Re-run this script (the SessionStart hook does so automatically,
# idempotently) to restore the daemon after a reboot/rebuild. On a host with a
# real crontab you may prefer register_cron.sh; the two are serialized by the
# same .fixer/lock, so running both never overlaps cycles.
#
# Idempotent & race-free via an flock the LOOP holds for its whole life:
#   - `exec 9>daemon.lock; flock -n 9` — if the lock is already held, a daemon is
#     running, so exit. Otherwise we hold it, hand fd 9 to the detached loop
#     (which inherits the same open file description and keeps the lock until it
#     dies), then release our own copy. A crashed daemon frees the lock
#     automatically, so re-launch just works — no stale pidfile, no PID-recycling
#     ambiguity, no fragile pgrep.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="${1:-${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}}}"
STATE="$PROJ/.fixer"
mkdir -p "$STATE"
MARKER="lint_fixer_daemon"  # in the loop's argv purely so a human `pgrep -f` finds it

# 1. Re-capture the authorized host. fixer_cycle.py compares socket.getfqdn() to
#    this file and returns early on a mismatch; after a container rebuild the old
#    value is stale, which would silently disable every cycle.
hostname -f > "$STATE/host"

# 2. Write the project-side entry stub. The loop calls THIS, never a versioned
#    plugin path: a long-lived daemon that exec'd its own start-time path would
#    keep running the version it was launched from long after an upgrade (this
#    happened — cron on 0.2.1 while the daemon ran 0.5.0). The stub re-resolves
#    the HIGHEST installed version at every tick, so an upgrade is picked up on
#    the next cycle with nothing to restart. `sort -V`, never mtime order.
#    (Written before the lock check: rewriting it for a running daemon is what
#    lets a plugin upgrade land without a restart.)
# 2b. The agent that runs the repair tiers. A SESSION knows which agent it is
# ($CLAUDE_CODE_EXECPATH / $CODEX_HOME); cron and the daemon inherit neither, so
# the choice is resolved HERE, at registration, and baked into the stub. Without
# this the cycle guesses from PATH order and can silently switch backends.
AGENT="${RESEARCH_NOTE_FIXER_AGENT:-}"
if [ -z "$AGENT" ]; then
    if [ -n "${CODEX_HOME:-}" ]; then AGENT=codex
    elif [ -n "${CLAUDE_CODE_EXECPATH:-}" ]; then AGENT=claude
    fi
fi

cat > "$STATE/run.sh" <<STUB
#!/usr/bin/env bash
# Resolve the HIGHEST installed plugin version at every tick — never a pinned
# path: a pin survives upgrades (the pinned version stays in the cache), so
# cron and the daemon kept executing months-old framework code while sessions
# used the new one. Falls back to the dir this stub was written from only when
# no plugin cache exists (project-side/legacy layout).
${AGENT:+export RESEARCH_NOTE_FIXER_AGENT=$AGENT}
D="\$(git -C "$PROJ" config --get research-note.pluginRoot 2>/dev/null)/fixer"
if [ ! -x "\$D/run_fixer.sh" ]; then
    D="\$(ls -d "\$HOME"/.codex/plugins/cache/*/research-note/*/fixer 2>/dev/null | sort -V | tail -1)"
fi
if [ ! -x "\$D/run_fixer.sh" ]; then
    D="\$(ls -d "\$HOME"/.claude/plugins/cache/*/research-note/*/fixer 2>/dev/null | sort -V | tail -1)"
fi
[ -n "\${D:-}" ] && [ -x "\$D/run_fixer.sh" ] || D="$HERE"
exec "\$D/run_fixer.sh" "$PROJ"
STUB
chmod +x "$STATE/run.sh"

if command -v flock >/dev/null 2>&1; then

# 3. Acquire the daemon lock (non-blocking). Held -> a daemon already runs.
exec 9> "$STATE/daemon.lock"
if ! flock -n 9; then
    echo "fixer daemon already running on $(cat "$STATE/host")"
    exit 0
fi

# 4. Launch the detached 5-min loop. It inherits fd 9 and thus holds the lock.
#    - `: $MARKER;` plants the marker in the loop's argv (human debugging only).
#    - `run.sh; sleep 600` (a `;`, never `&&`): even if a cycle crashes the loop
#      always sleeps before retrying — never a tight loop.
#    - run_fixer.sh's own `flock -n lock` serializes cycles, so a long analyze
#      agent just makes the next tick skip; cycles never pile up.
setsid nohup bash -c ": $MARKER; while true; do \"$STATE/run.sh\"; sleep 600; done" \
    >> "$STATE/cron.log" 2>&1 &
disown 2>/dev/null || true

# 5. Release our own copy of the lock so only the loop holds it, then verify: a
#    fresh non-blocking acquire from a subshell must FAIL (loop alive) — if it
#    SUCCEEDS, the loop died and nobody holds the lock.
sleep 1
exec 9>&-
if bash -c 'exec 9>"'"$STATE"'/daemon.lock"; flock -n 9' 2>/dev/null; then
    echo "WARNING: fixer daemon failed to start — check $STATE/cron.log" >&2
    exit 1
fi
echo "fixer daemon started on $(cat "$STATE/host")"

else

# macOS ships neither flock(1) nor setsid(1). Same design, python plumbing:
# a tiny supervisor takes daemon.lock via fcntl and HOLDS it for the loop's
# whole life (crash frees it automatically, same as the fd-9 scheme), and
# nohup+& detaches it from the session.
lock_free() {
    /usr/bin/python3 -c '
import fcntl, sys
f = open(sys.argv[1], "w")
try:
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)
' "$STATE/daemon.lock" 2>/dev/null
}

if ! lock_free; then
    echo "fixer daemon already running on $(cat "$STATE/host")"
    exit 0
fi

nohup /usr/bin/python3 -c '
import fcntl, os, subprocess, sys, time
state = sys.argv[1]
lock = open(os.path.join(state, "daemon.lock"), "w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(0)                            # lost the start race: daemon already up
while True:                                # run.sh then sleep, even on a crash —
    subprocess.run([os.path.join(state, "run.sh")])
    time.sleep(600)                        # never a tight loop
' "$STATE" "$MARKER" >> "$STATE/cron.log" 2>&1 &
disown 2>/dev/null || true

sleep 1
if lock_free; then
    echo "WARNING: fixer daemon failed to start — check $STATE/cron.log" >&2
    exit 1
fi
echo "fixer daemon started on $(cat "$STATE/host")"

fi
