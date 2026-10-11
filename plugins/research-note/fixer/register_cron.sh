#!/usr/bin/env bash
# Register (or re-register) the page-fixer cron for one project on THIS node.
# Usage: register_cron.sh [PROJECT_DIR] [CADENCE_MINUTES]   (defaults: legacy layout, 10)
# Run once per project, and again after migrating to a new node — it auto-captures
# the current host so nothing is hardcoded. Idempotent: safe to re-run.
#
# THIS SCRIPT IS FOR A HOST WITH A REAL `crontab`. Without one, use
# start_fixer_daemon.sh instead (the SessionStart hook launches it automatically).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="${1:-${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}}}"
CADENCE="${2:-10}"
STATE="$PROJ/.fixer"
mkdir -p "$STATE"

# 1. Capture the authorized host (gitignored; the fixer's runtime guard reads it).
hostname -f > "$STATE/host"
HOST="$(cat "$STATE/host")"

# 2. The crontab line calls the project-side stub — it re-resolves this
# project's pinned runtime at every tick, so project updates need no
# re-registration. A highest-installed-cache lookup remains only for legacy
# projects without a valid pin.
# The stub is DERIVED, so it is rewritten unconditionally on every
# registration, exactly like start_fixer_daemon.sh does on every start: an
# exists-guard here once stranded stubs across the 0.9.0 plugin rename — they
# kept resolving the retired name's cache copy and died when it was pruned.
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
# Resolve this project's pinned plugin at every tick. Legacy projects without
# a project pin use the directory this stub was written from.
${AGENT:+export RESEARCH_NOTE_FIXER_AGENT=$AGENT}
P="\$(git -C "$PROJ" config --get research-note.pluginRoot 2>/dev/null)"
if [ -n "\$P" ]; then
    D="\$P/fixer"
elif [ ! -f "$PROJ/.research-note/plugin-lock.json" ]; then
    D="$HERE"
else
    echo "fixer: restore this project's plugin lock before running" >&2
    exit 2
fi
[ -x "\$D/run_fixer.sh" ] || { echo "fixer: selected plugin is missing" >&2; exit 2; }
exec "\$D/run_fixer.sh" "$PROJ"
STUB
chmod +x "$STATE/run.sh"

# 3. Install the cron line, replacing any prior entry for THIS project (no
# duplicates; other projects' fixer lines are left alone).
# `|| true` on the grep is load-bearing: when the ONLY existing line is our own,
# grep -v matches nothing and exits 1, which under `set -e` would abort the
# subshell before echo and wipe the crontab. Guard it.
LINE="*/$CADENCE * * * * $STATE/run.sh >> $STATE/cron.log 2>&1"
{ crontab -l 2>/dev/null | grep -v -e "run_fixer.sh $PROJ" -e "$STATE/run.sh" || true; echo "$LINE"; } | crontab -

echo "fixer cron registered on $HOST (every $CADENCE min)"
echo "  $LINE"
