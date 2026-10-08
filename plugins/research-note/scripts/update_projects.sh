#!/usr/bin/env bash
# update_projects.sh — update explicitly selected projects to one pinned runtime.
#
# Usage: update_projects.sh [--dry-run] [--latest [--ref REF]] [<project-dir> ...]
# With no directory, use the current project. The public wrapper snapshots the
# source, syncs contracts and hooks transactionally, and binds BOTH agents only
# in that project. It never upgrades either host's user installation.
# Legacy --agents / --no-cross-agent options are accepted; project bindings now
# always share one version. --latest fetches source into a temporary checkout.
# Does not commit or reload running sessions. Start new sessions after updating.
set -uo pipefail

# The public entry point stages an immutable runtime and rolls back a failed
# project update. The internal pass never updates either agent's user install.
if [ "${RN_RUNTIME_UPDATE_INTERNAL:-}" != 1 ]; then
    runtime_here=$(cd "$(dirname "$0")" && pwd -P)
    exec python3 "$runtime_here/project_runtime.py" update --source "$runtime_here/.." "$@"
fi

DRY=0; AGENTS=both; declare -a WANT=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        --agents)
            shift
            [ "$#" -gt 0 ] || {
                echo "update_projects: --agents wants both, claude, codex, or none" >&2
                exit 2
            }
            AGENTS=$1
            case "$AGENTS" in
                both|claude|codex|none) ;;
                *) echo "update_projects: --agents wants both, claude, codex, or none" >&2; exit 2 ;;
            esac ;;
        --no-cross-agent) AGENTS=none ;;  # compatibility with the old spelling
        -*) echo "update_projects: unknown flag $1" >&2; exit 2 ;;
        *) WANT+=("$1") ;;
    esac
    shift
done

# The invoked script carries the framework version it deploys. Resolving only
# through ~/.claude made the same package unusable on a Codex-only machine and
# could silently choose a version other than the caller invoked.
HERE=$(cd "$(dirname "$0")" && pwd -P)
CACHE=$(cd "$HERE/.." && pwd -P)
VER=$(python3 - "$CACHE" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for manifest in (root / ".codex-plugin/plugin.json", root / ".claude-plugin/plugin.json"):
    if manifest.is_file():
        print(json.loads(manifest.read_text())["version"])
        break
else:
    raise SystemExit(2)
PY
) || { echo "update_projects: cannot read plugin version from $CACHE" >&2; exit 2; }
echo "target version: $VER   ($CACHE)"

if [ ${#WANT[@]} -eq 0 ]; then
    cur=${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}}
    [ -n "$cur" ] && WANT+=("$cur")
fi
# Guarded before the expansion: an empty array under `set -u` is an "unbound
# variable" abort in bash 3.2, which would report a missing registry as a shell
# error.
[ ${#WANT[@]} -gt 0 ] || {
    echo "update_projects: not inside a project; run it from the project, or pass its path" >&2
    exit 2
}
echo "projects: ${WANT[*]}"

run() { [ "$DRY" = 1 ] && { echo "   would: $*"; return 0; }; "$@"; }
CHANGED=()

for P in "${WANT[@]}"; do
    echo
    echo "=== $P"
    # The two-marker test projroot.py uses, not a bare `.claude` probe: the
    # user's HOME carries ~/.claude (credentials, plugins, jobs — the global
    # config dir), and a session ever started there leaves a projectPath row
    # in installed_plugins.json. Gated only on `.claude` existing, this loop
    # then wrote contract files into $HOME and rewrote the enclosing repo's
    # hooksPath — found by a cluster session one command before doing it.
    if [ ! -d "$P/project_memory" ] || { [ ! -f "$P/.research-note/project.json" ] \
            && [ ! -f "$P/.claude/framework.json" ] && [ ! -f "$P/.claude/roles.json" ]; }; then
        echo "   not a framework project (needs project_memory/ + .research-note/project.json or .claude/framework.json) — skipped"
        continue
    fi

    # --- migrate once, then read what this project enables. A project from
    # before the declaration gets .research-note/project.json with every
    # integration ON — exactly what it had — and the core state dir's ignore;
    # an update never disables anything. Under --dry-run the ownership table
    # says, before any step runs, who owns each managed path and what may
    # happen to it.
    CONFLICTS=0
    HPC_ON=true
    if [ -f "$CACHE/scripts/project_config.py" ]; then
        init_out=$(python3 "$CACHE/scripts/project_config.py" --project "$P" init $([ "$DRY" = 1 ] && echo --dry-run) 2>&1) || exit $?
        printf '%s\n' "$init_out" | grep -vE '^kept ' | sed 's/^/   /'
        printf '%s\n' "$init_out" | grep -qE '^(migrated|new) ' && CHANGED+=("$P")
        if [ "$DRY" = 1 ]; then
            echo "   ownership — what this update may touch, and how:"
            python3 "$CACHE/scripts/project_config.py" --project "$P" ownership 2>/dev/null \
                | awk -F'\t' '{ printf "      %-58s %-30s %s\n", $1, $2, $3 }'
        fi
        HPC_ON=$(python3 "$CACHE/scripts/project_config.py" --project "$P" feature hpc 2>/dev/null || echo true)
    fi

    echo "   host plugins: activated together by the project runtime transaction"

    # --- the four contracts have a framework section followed by the project's
    # editable appendix. contracts.py updates the first and preserves the
    # second. Older .research-note/rules/<x>.md files are imported once for
    # compatibility; an edited framework section is reported as CONFLICT.
    if [ -f "$CACHE/scripts/contracts.py" ]; then
        ct_out=$(python3 "$CACHE/scripts/contracts.py" sync "$P" --plugin "$CACHE" $([ "$DRY" = 1 ] && echo --dry-run) 2>&1) || exit $?
        printf '%s\n' "$ct_out" | grep -vE '^same ' | sed 's/^/   contract: /'
        printf '%s\n' "$ct_out" | grep -qE '^(new|migrated|generated|regenerated) ' && CHANGED+=("$P")
        CONFLICTS=$(( CONFLICTS + $(printf '%s\n' "$ct_out" | grep -c '^CONFLICT ') ))
    fi

    # --- framework.json is STATE + policy, never synced wholesale: `record` is
    # the project's migration marker (the linters' FW gate reads it), so copying
    # the template's value would mark an unmigrated record as current and disarm
    # the one check that protects it. Report drift; migration moves the marker.
    if [ -f "$P/.claude/framework.json" ] && [ -f "$CACHE/templates/framework.json" ]; then
        pr=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('record',''))" "$P/.claude/framework.json" 2>/dev/null)
        tr_=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('record',''))" "$CACHE/templates/framework.json" 2>/dev/null)
        if [ "$pr" != "$tr_" ]; then
            echo "   conflict: framework.json record '$pr' (template '$tr_') — LEFT ALONE; migrate the record, then bump the marker"
            CONFLICTS=$(( CONFLICTS + 1 ))
        fi
    fi

    # --- page templates: framework text — copied over; the record contract
    # points at them.
    if ls "$CACHE"/design/*-template.md >/dev/null 2>&1; then
        run mkdir -p "$P/.claude/examples" || exit $?
        for ex in "$CACHE"/design/*-template.md; do
            b=$(basename "$ex")
            if [ ! -f "$P/.claude/examples/$b" ] || ! diff -q "$ex" "$P/.claude/examples/$b" >/dev/null 2>&1; then
                run cp "$ex" "$P/.claude/examples/$b" || exit $?; echo "   example: $b synced"; CHANGED+=("$P")
            fi
        done
    fi

    # --- githooks: the dispatcher and research-note's own checks are framework
    # text, installed and refreshed by the one module that knows the layout. It
    # migrates a pre-dispatcher project (real files under the hook names), keeps
    # forwarding to whatever hooks were active before research-note took
    # core.hooksPath, and leaves a pre-declaration commit-msg alone with a
    # warning: that hook carries the project's own layer rows until they move
    # into .research-note/project.json.
    if [ -f "$CACHE/scripts/githooks_install.py" ]; then
        gh_out=$(python3 "$CACHE/scripts/githooks_install.py" install "$P" --plugin "$CACHE" $([ "$DRY" = 1 ] && echo --dry-run) 2>&1) || exit $?
        printf '%s\n' "$gh_out" | grep -vE '^kept ' | sed 's/^/   githook: /'
        printf '%s\n' "$gh_out" | grep -qE '^(new|synced|moved|linked) ' && CHANGED+=("$P")
        CONFLICTS=$(( CONFLICTS + $(printf '%s\n' "$gh_out" | grep -c '^WARN ') ))
    fi

    # --- pluginRoot is the one git config an update must REPOINT rather than
    # merely fill. It holds an absolute path INTO the version directory, so a
    # scope pinned to the new version with pluginRoot still on the old one runs
    # the new skills over the OLD scripts — both linters, the record bus, the
    # submit launchers and the fixer stub's first branch all resolve $PLUGIN
    # through it. Measured: three pins moved to 0.15.0 and every $PLUGIN script
    # kept executing 0.14.2, because only bootstrap_project.py wrote this key
    # and an update never called it. Unlike core.hooksPath above — a project
    # decision, filled only when empty — this is a plugin fact, so it is
    # overwritten every run.
    pr=$(git -C "$P" config --get research-note.pluginRoot 2>/dev/null)
    if [ "$pr" != "$CACHE" ]; then
        run git -C "$P" config research-note.pluginRoot "$CACHE" || exit $?
        echo "   research-note.pluginRoot -> $CACHE${pr:+   (was $pr)}"
    fi

    # --- permissions merge one way only: what the TEMPLATE gained is a new
    # mechanism's requirement; what the PROJECT has is a machine fact and stays.
    if [ -f "$CACHE/templates/settings.json" ] && [ -f "$P/.claude/settings.json" ]; then
        hpc_perms=""
        [ "$HPC_ON" = true ] && [ -f "$CACHE/templates/hpc-permissions.json" ] && hpc_perms="$CACHE/templates/hpc-permissions.json"
        added=$(DRY=$DRY python3 - "$CACHE/templates/settings.json" "$P/.claude/settings.json" "$hpc_perms" <<'PY'
import json, os, sys
tpl, proj, hpc = sys.argv[1], sys.argv[2], sys.argv[3]
t = json.load(open(tpl)).get("permissions", {}).get("allow", [])
if hpc:
    t = t + [r for r in json.load(open(hpc)) if r not in t]   # the cluster's commands, for a project that has a cluster
s = json.load(open(proj)); a = s.setdefault("permissions", {}).setdefault("allow", [])
new = [k for k in t if k not in a]
if new and os.environ.get("DRY") != "1":
    a.extend(new)
    json.dump(s, open(proj, "w"), indent=2); open(proj, "a").write("\n")
print(" ".join(new))
PY
) || exit $?
        [ -n "$added" ] && { echo "   permissions added: $added"; CHANGED+=("$P"); }
    fi

    if [ "$HPC_ON" = true ]; then
        # --- hpc.env: KEYS only, never values. A key the template documents and the
        # project lacks is a capability the project silently does not have.
        if [ -f "$CACHE/templates/hpc.env" ] && [ -f "$P/.claude/hpc.env" ]; then
            miss=$(grep -oE '^#?[A-Z_]+=' "$CACHE/templates/hpc.env" | tr -d '#=' | sort -u | while read -r k; do
                       grep -qE "^$k=" "$P/.claude/hpc.env" || echo "$k"; done | tr '\n' ' ')
            [ -n "${miss// /}" ] && echo "   hpc.env: template documents keys this project lacks — $miss (values are yours to give)"
        fi

        # --- derived submit templates: report, never overwrite. The log header is
        # the framework's; the resources and the script/args lines are the node's.
        for s in cpu_batch.slurm gpu_batch.slurm; do
            [ -f "$P/.claude/hpc-submit/$s" ] && [ -f "$CACHE/skills/hpc-submit/scripts/$s" ] || continue
            diff -q "$CACHE/skills/hpc-submit/scripts/$s" "$P/.claude/hpc-submit/$s" >/dev/null 2>&1 || {
                echo "   conflict: submit template $s differs from the plugin's — port the header block by hand (see the skill)"
                CONFLICTS=$(( CONFLICTS + 1 )); }
        done
    else
        # a disabled integration is retained, not repaired: its files stay as they are
        echo "   hpc: disabled in .research-note/project.json — hpc.env, submit templates and cluster permissions left as they are"
    fi

    [ "$CONFLICTS" -gt 0 ] && echo "   $CONFLICTS item(s) above need a person — nothing was overwritten there"

    # --- verify: the machinery, then the pages.
    if [ "$DRY" != 1 ]; then
        ( cd "$P" && CLAUDE_PROJECT_DIR="$P" bash "$CACHE/scripts/doctor.sh" >/tmp/.doc.$$ 2>&1 )
        tail -1 /tmp/.doc.$$ | sed 's/^/   doctor: /'
        grep -E '✗|!' /tmp/.doc.$$ | sed 's/^/   /' | head -6; rm -f /tmp/.doc.$$
        # BOTH linters. Only the node one ran here, so every objective rule
        # that tightened after this step was written — O13 and O14 both — went
        # out to every project without a single objective page ever being read
        # by the new linter. Catching that is the ONLY thing this step is for:
        # a relaxed rule cannot break a green page, a tightened one can, and an
        # update is the moment it would show.
        nlint=$( cd "$P" && CLAUDE_PROJECT_DIR="$P" python3 "$CACHE/scripts/check_node_page.py" --cross --quiet 2>&1 )
        olint=$( cd "$P" && CLAUDE_PROJECT_DIR="$P" python3 "$CACHE/scripts/check_objective_page.py" --quiet 2>&1 )
        # Deduped: FW is emitted by both linters, and a project mid-migration
        # would otherwise report its one expected finding twice.
        lint=$( printf '%s\n%s\n' "$nlint" "$olint" | grep -v '^[[:space:]]*$' | awk '!seen[$0]++' | head -8 )
        [ -n "$lint" ] && { echo "   lint:"; printf '%s\n' "$lint" | sed 's/^/     /'; } || echo "   lint: pages green"
    fi
done

# --- What the CALLING SESSION must read to be current. A session cannot reload
# itself, but it can read: the files below are the ones whose content it is
# acting on, served from whatever version it loaded at launch. Reading them puts
# the published text in context, which is what the session then follows.
echo
echo "the session invoking this should now READ, to be current with $VER:"
for f in skills/update/SKILL.md skills/analyze/SKILL.md skills/objective/SKILL.md \
         skills/hpc-submit/SKILL.md skills/plan/SKILL.md; do
    [ -f "$CACHE/$f" ] || continue
    # Only the ones that actually changed since the version the caller may hold:
    # git in the plugin repo knows, but the cache does not, so name the skills
    # this update touched by comparing against the previous cached version.
    # Siblings in THIS marketplace only: versions do not compare across
    # marketplaces — a repository renamed and re-registered restarts its
    # numbering, and a leftover 0.31 would outrank a current 0.2.
    PREV=$(ls -d "$(dirname "$CACHE")"/* 2>/dev/null \
           | grep -Fvx "$CACHE" | sort -V | tail -1)
    if [ -n "$PREV" ] && [ "$PREV" != "$CACHE" ] && ! diff -q "$PREV/$f" "$CACHE/$f" >/dev/null 2>&1; then
        echo "   $CACHE/$f      (changed in $VER)"
    fi
done
echo "   plus any contract file listed as synced above (those cannot be reloaded at all)"

echo
if [ ${#CHANGED[@]} -gt 0 ]; then
    printf '%s\n' "${CHANGED[@]}" | sort -u | while read -r p; do
        echo "review and commit the agent-layer changes in $p (.claude, .codex, .research-note)"
    done
    echo
    echo "Start new Claude and Codex sessions in this project after activation."
    echo "Contract files cannot be reloaded — Read the ones listed as synced above."
else
    echo "nothing to sync — every project already on $VER"
fi

