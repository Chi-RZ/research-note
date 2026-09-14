#!/usr/bin/env bash
# Cron entry for the page fixer — all logic lives in fixer_cycle.py.
# Usage: run_fixer.sh [PROJECT_DIR]
#   PROJECT_DIR resolution: $1 -> $RESEARCH_NOTE_PROJECT_DIR ->
#   $CLAUDE_PROJECT_DIR -> legacy layout (this
#   script at <project>/.claude/fixer/). Runtime state lives in
#   <project>/.fixer/ (survives plugin upgrades; the code dir may be versioned).
# crontab: */10 * * * * <path>/run_fixer.sh <project> >> <project>/.fixer/cron.log 2>&1
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="${1:-${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}}}"
export RESEARCH_NOTE_PROJECT_DIR="$PROJ"
export CLAUDE_PROJECT_DIR="$PROJ"
STATE="$PROJ/.fixer"
mkdir -p "$STATE"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
unset VIRTUAL_ENV

# A Claude VS Code-server binary is not normally on PATH. Resolve it when
# present; fixer_cycle.py can otherwise use Codex and chooses the active agent
# automatically (override with RESEARCH_NOTE_FIXER_AGENT=claude|codex).
CLAUDE_BIN="${CLAUDE_CODE_EXECPATH:-}"
[ -x "$CLAUDE_BIN" ] || CLAUDE_BIN=$(ls -t "$HOME"/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null | head -1)
[ -n "${CLAUDE_BIN:-}" ] && [ -x "$CLAUDE_BIN" ] && export PATH="$(dirname "$CLAUDE_BIN"):$PATH"

# Serialize cycles: flock(2) on fd 9, non-blocking — if another cycle holds it,
# this tick just skips. python3, not flock(1), because macOS ships none. The
# lock lives on the open file description, so `exec` below inherits it and the
# cycle holds it for its whole life; a crash frees it automatically.
exec 9>"$STATE/lock"
/usr/bin/python3 -c 'import fcntl, sys
try: fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError: sys.exit(1)' || exit 0     # another cycle is running
exec /usr/bin/python3 "$HERE/fixer_cycle.py"
