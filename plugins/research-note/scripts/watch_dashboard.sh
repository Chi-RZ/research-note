#!/usr/bin/env bash
# Regenerate the Q dashboard whenever a question page changes.
# Poll-based (this cluster has no inotifywait): hashes the mtime+path set of
# every Q-*.md under questions/ every 2 s and regenerates on any change
# (edit / add / delete / move between open<->answered). Live Preview then
# auto-refreshes the browser. Ctrl-C to stop.
#
# Honours $DASHBOARD_REMOTE_HOST (VSCode Remote-SSH host alias) if set, so
# jump links point at the remote q-pages.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT" || exit 1

GEN=".claude/scripts/gen_dashboard.py"
QDIR="project_memory/questions"
INTERVAL="${DASHBOARD_WATCH_INTERVAL:-2}"

gen() {
  if [ -n "${DASHBOARD_REMOTE_HOST:-}" ]; then
    python3 "$GEN" --remote-host "$DASHBOARD_REMOTE_HOST"
  else
    python3 "$GEN"
  fi
}
# GNU find has -printf; BSD (macOS) falls back to stat. cksum is POSIX on both.
sig() {
  { find "$QDIR" -name 'Q-*.md' -printf '%T@ %p\n' 2>/dev/null \
    || find "$QDIR" -name 'Q-*.md' -exec stat -f '%m %N' {} + 2>/dev/null; } | cksum
}

echo "[watch_dashboard] watching $QDIR (every ${INTERVAL}s) — Ctrl-C to stop"
gen
last="$(sig)"
while true; do
  sleep "$INTERVAL"
  now="$(sig)"
  if [ "$now" != "$last" ]; then
    last="$now"
    gen
  fi
done
