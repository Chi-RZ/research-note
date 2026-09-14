#!/usr/bin/env bash
# update_projects.sh — do the mechanical half of research-note:update, for every
# project on the framework, in one command.
#
# Why a script and not just the skill's prose: a script is a separate process
# that reads the newest file every run, so it needs no /reload-plugins to be
# current. The skill's steps kept being executed by hand, and the same three
# mistakes kept recurring — a scope updated from the wrong directory, a
# permission the template had gained left unmerged, a contract file synced but
# never re-read. Those are mechanical, so they belong here; what is left in the
# skill is the judgment (a project-specific hunk, a .slurm header to port).
#
# Usage: update_projects.sh [--dry-run] [--agents both|claude|codex|none]
#                           [<project-dir> ...]
#        (no dirs: neutral registry + legacy Claude project rows)
#
# Does NOT: commit (it prints what to commit; staging is the caller's), or
# reload the session (impossible from a script — see the skill's step 5).
set -uo pipefail

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

CLAUDE_REGISTRY="$HOME/.claude/plugins/installed_plugins.json"
# The plugin's Claude selector, `research-note@<marketplace>`, read from the
# registry rather than spelled. The marketplace NAME is the installer's, not
# ours: it is whatever `claude plugin marketplace add` registered, and on any
# machine but the author's that is not the name this repo happens to declare.
# Hardcoding it made the project-scope update below a no-op there — silently,
# since a selector that matches nothing is not an error. The block that reads
# the pin back, twenty lines down, has always derived it correctly.
CLAUDE_SELECTOR=$(python3 - "$CLAUDE_REGISTRY" 2>/dev/null <<'PY' || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit
for key in d.get("plugins", {}):
    if key.split("@", 1)[0] == "research-note":
        print(key)
        break
PY
)
PROJECT_REGISTRY="$HOME/.config/research-note/projects.json"

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
echo "agents: $AGENTS"

if [ ${#WANT[@]} -eq 0 ]; then
    # `while read`, not mapfile: mapfile is a bash 4 builtin and macOS ships
    # 3.2, so this script died on its first line of real work there. The loop
    # is the same operation in the language every bash speaks.
    while IFS= read -r p; do WANT+=("$p"); done < <(
        python3 - "$PROJECT_REGISTRY" "$CLAUDE_REGISTRY" <<'PY'
import json, sys
from pathlib import Path

projects = set()
neutral, legacy = map(Path, sys.argv[1:])
if neutral.is_file():
    try:
        projects.update(json.loads(neutral.read_text()).get("projects", []))
    except (OSError, ValueError):
        pass
if legacy.is_file():
    try:
        data = json.loads(legacy.read_text())
    except (OSError, ValueError):
        data = {}
    for key, rows in data.get("plugins", {}).items():
        if key.split("@")[0] != "research-note":
            continue
        for row in rows:
            p = row.get("projectPath")
            if p:
                projects.add(p)
for p in sorted(projects):
    # Managed worktrees are ephemeral views, not independent projects.
    if "/.claude/worktrees/" not in p:
        print(p)
PY
    )
fi
# Guarded before the expansion: an empty array under `set -u` is an "unbound
# variable" abort in bash 3.2, which would report a missing registry as a shell
# error.
[ ${#WANT[@]} -gt 0 ] || {
    echo "update_projects: no framework project registered; pass a project path or run bootstrap_project.py once" >&2
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
    if [ ! -d "$P/project_memory" ] || { [ ! -f "$P/.claude/framework.json" ] \
            && [ ! -f "$P/.claude/roles.json" ]; }; then
        echo "   not a framework project (needs project_memory/ + .claude/framework.json) — skipped"
        continue
    fi

    # Claude has project-scoped plugin pins; Codex installs plugins at machine
    # scope. Project framework sync itself depends on neither registry.
    if { [ "$AGENTS" = both ] || [ "$AGENTS" = claude ]; } \
            && command -v claude >/dev/null 2>&1 \
            && [ -f "$CLAUDE_REGISTRY" ]; then
        # No selector means no row to update; the read-back below reports it.
        [ -n "$CLAUDE_SELECTOR" ] && \
            ( cd "$P" && run claude plugin update "$CLAUDE_SELECTOR" --scope project >/dev/null 2>&1 )
        got=$(python3 - "$CLAUDE_REGISTRY" "$P" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for key, rows in d.get("plugins", {}).items():
    if key.split("@")[0] != "research-note":
        continue
    for e in rows:
        if e.get("projectPath") == sys.argv[2]:
            print(e.get("version", "?"))
            raise SystemExit
print("(no row)")
PY
        )
        # A pin AHEAD of this copy is the normal state right after an update —
        # the script executing is the old version by construction. Only a pin
        # BEHIND is a finding.
        if [ "$got" = "$VER" ]; then
            echo "   claude project pin: $VER"
        elif [ "$(printf '%s\n%s\n' "$VER" "$got" | sort -V | tail -1)" = "$got" ]; then
            echo "   claude project pin: $got  (ahead of this copy $VER — fine)"
        else
            echo "   claude project pin: $got  ← BEHIND this copy $VER (verify by hand)"
        fi
    else
        echo "   claude project pin: skipped"
    fi

    # --- framework text: copy when it drifts. A hunk that is this project's own
    # decision is the skill's judgment call, not this script's; it reports the
    # drift so the caller can look before the copy lands in a commit.
    for f in CLAUDE.md experiments-CLAUDE.md wiki-CLAUDE.md project_memory-CLAUDE.md; do
        [ -f "$CACHE/templates/$f" ] || continue
        if [ ! -f "$P/.claude/$f" ]; then
            run cp "$CACHE/templates/$f" "$P/.claude/$f"; echo "   contract: $f CREATED"; CHANGED+=("$P")
        elif ! diff -q "$CACHE/templates/$f" "$P/.claude/$f" >/dev/null 2>&1; then
            n=$(diff "$CACHE/templates/$f" "$P/.claude/$f" | grep -c '^[<>]')
            # A project may APPEND its own bindings under the framework text (a
            # layout table, extra commit prefixes). When the template is still a
            # byte-prefix of the project's copy, the framework half is already
            # current and the whole diff is that appendix — copying would delete
            # it, which is a deletion wearing a sync's clothes. Report instead.
            tl=$(wc -l < "$CACHE/templates/$f")
            pl=$(wc -l < "$P/.claude/$f")
            if head -n "$tl" "$P/.claude/$f" | diff -q - "$CACHE/templates/$f" >/dev/null 2>&1; then
                echo "   contract: $f framework text is CURRENT; the project appends $((pl - tl)) own line(s) below it — left alone"
            elif [ "$pl" -gt "$tl" ]; then
                # Longer AND the prefix does not match: the framework text drifted
                # under content this project added. A copy would carry the drift
                # forward and drop the addition in the same stroke, so neither half
                # can be done blind.
                echo "   contract: $f DRIFTED under $((pl - tl)) project-added line(s) — port by hand, a copy would drop them"
                echo "      diff $CACHE/templates/$f $P/.claude/$f"
            else
                run cp "$CACHE/templates/$f" "$P/.claude/$f"; echo "   contract: $f synced ($n differing lines)"; CHANGED+=("$P")
            fi
        fi
    done

    # --- framework.json is STATE + policy, never synced wholesale: `record` is
    # the project's migration marker (the linters' FW gate reads it), so copying
    # the template's value would mark an unmigrated record as current and disarm
    # the one check that protects it. Report drift; migration moves the marker.
    if [ -f "$P/.claude/framework.json" ] && [ -f "$CACHE/templates/framework.json" ]; then
        pr=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('record',''))" "$P/.claude/framework.json" 2>/dev/null)
        tr_=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('record',''))" "$CACHE/templates/framework.json" 2>/dev/null)
        if [ "$pr" != "$tr_" ]; then
            echo "   framework.json: record '$pr' (template '$tr_') — LEFT ALONE; migrate the record, then bump the marker"
        fi
    fi

    # --- page templates: framework text — copied over; the record contract
    # points at them.
    if ls "$CACHE"/design/*-template.md >/dev/null 2>&1; then
        mkdir -p "$P/.claude/examples"
        for ex in "$CACHE"/design/*-template.md; do
            b=$(basename "$ex")
            if [ ! -f "$P/.claude/examples/$b" ] || ! diff -q "$ex" "$P/.claude/examples/$b" >/dev/null 2>&1; then
                run cp "$ex" "$P/.claude/examples/$b"; echo "   example: $b synced"; CHANGED+=("$P")
            fi
        done
    fi

    # --- githooks: install a MISSING one, never overwrite an existing one.
    # A guard that never reached the project is a guard that never fires, so a
    # hook the project lacks is pure gain. But commit-msg's RULES table maps each
    # prefix to the top-level dirs it may touch, which makes it a function of the
    # project's LAYOUT: every project whose tree exceeds the template's five dirs
    # has extended it legitimately. Copying over that is not a sync, it is a
    # deletion — the prefixes vanish and every commit touching those dirs is
    # rejected until someone works out why. Porting a plugin-side change into a
    # customised hook needs judgment, so the script reports and the skill decides.
    if [ -d "$CACHE/githooks" ]; then
        mkdir -p "$P/.claude/githooks"
        for h in "$CACHE"/githooks/*; do
            [ -f "$h" ] || continue
            b=$(basename "$h")
            if [ ! -e "$P/.claude/githooks/$b" ]; then
                run cp "$h" "$P/.claude/githooks/$b"; echo "   githook: $b installed (was missing)"; CHANGED+=("$P")
            elif ! diff -q "$h" "$P/.claude/githooks/$b" >/dev/null 2>&1; then
                echo "   githook: $b DIFFERS from the template — diff and port by hand"
                echo "      diff $h $P/.claude/githooks/$b"
            fi
        done
        hp=$(git -C "$P" config core.hooksPath 2>/dev/null)
        [ -n "$hp" ] || { run git -C "$P" config core.hooksPath .claude/githooks; echo "   githook: core.hooksPath set"; }
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
        run git -C "$P" config research-note.pluginRoot "$CACHE"
        echo "   research-note.pluginRoot -> $CACHE${pr:+   (was $pr)}"
    fi

    # --- permissions merge one way only: what the TEMPLATE gained is a new
    # mechanism's requirement; what the PROJECT has is a machine fact and stays.
    if [ -f "$CACHE/templates/settings.json" ] && [ -f "$P/.claude/settings.json" ]; then
        added=$(DRY=$DRY python3 - "$CACHE/templates/settings.json" "$P/.claude/settings.json" <<'PY'
import json, os, sys
tpl, proj = sys.argv[1], sys.argv[2]
t = json.load(open(tpl)).get("permissions", {}).get("allow", [])
s = json.load(open(proj)); a = s.setdefault("permissions", {}).setdefault("allow", [])
new = [k for k in t if k not in a]
if new and os.environ.get("DRY") != "1":
    a.extend(new)
    json.dump(s, open(proj, "w"), indent=2); open(proj, "a").write("\n")
print(" ".join(new))
PY
)
        [ -n "$added" ] && { echo "   permissions added: $added"; CHANGED+=("$P"); }
    fi

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
        diff -q "$CACHE/skills/hpc-submit/scripts/$s" "$P/.claude/hpc-submit/$s" >/dev/null 2>&1 || \
            echo "   submit template $s differs from the plugin's — port the header block by hand (see the skill)"
    done

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

# --- Selected agents, each through its own native registry, against ORIGIN.
# A clean git-backed Claude marketplace is advanced with pull --ff-only because
# Claude's native refresh deletes and reclones it. Codex owns disposable
# snapshots, so its native upgrade is safe. Non-git Claude sources also use the
# native refresh because there is no editable checkout to preserve.
AGENT_SYNC_FAILED=0
RESOLVED_F=$(mktemp)
if [ "$AGENTS" != none ]; then
python3 - "$CACHE" "$DRY" "$HERE" "$AGENTS" "$RESOLVED_F" <<'PY' || AGENT_SYNC_FAILED=1
import json, os, shutil, subprocess, sys
from pathlib import Path

cache, dry, here = Path(sys.argv[1]), sys.argv[2] == "1", Path(sys.argv[3])
choice = sys.argv[4]
resolved_f = Path(sys.argv[5])
agents = ("claude", "codex") if choice == "both" else (choice,)
# This script's OWN sibling first, $CACHE second. In an install the two are the
# same file; they differ only when the script is run out of a checkout, and
# then the sibling is the one that matches this script's expectations.
sys.path[:0] = [str(here), str(cache / "scripts")]
try:
    import bootstrap_project as b
    b.marketplace_head, b.installed, b._marketplaces   # required by this block
except Exception:
    sys.exit(0)
try:
    running = json.loads((cache / ".claude-plugin" / "plugin.json").read_text())["version"]
except Exception:
    sys.exit(0)


def published(root):
    """The version the marketplace SOURCE offers, or None.

    NOT the version of the copy executing this script. Those are the same only
    until someone publishes; after that the running copy is by definition the
    OLD one, and asking "is the agent on my version?" answers "yes" forever —
    an updater that can never pull anything newer than itself. That is exactly
    how 0.25.0 shipped and Claude stayed on 0.24.0: its marketplace root is the
    local source repo, so `local == remote` held too, and both staleness tests
    were false at once.
    """
    if not root:
        return None
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        m = Path(root) / "plugins" / "research-note" / rel
        if m.is_file():
            try:
                return json.loads(m.read_text())["version"]
            except Exception:
                return None
    return None


def state(agent):
    """(version, marketplace, ref, local HEAD, origin HEAD) or None if absent."""
    rows = [r for r in b.installed(agent) if r["id"].split("@")[0] == "research-note"]
    if not rows:
        return None
    mkt = rows[0]["id"].split("@", 1)[1]
    row = next((m for m in b._marketplaces(agent) if m.get("name") == mkt), {})
    local, remote = b.marketplace_head(row.get("root"), row.get("ref"))
    return rows[0]["version"], mkt, row.get("ref"), local, remote, row.get("root")


def show(agent, st):
    ver, mkt, ref, local, remote, _root = st
    if local and remote:
        where = "== origin" if local == remote else f"!= origin {remote[:7]}"
    else:
        where = "origin unknown"
    print(f"   {agent:6}: {ver:24} {mkt}@{ref or '?'} {(local or '?')[:7]}  {where}")


def invoke(cmd):
    if dry:
        print("      would: " + " ".join(map(str, cmd)))
        return True
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                       stdin=subprocess.DEVNULL)
    if r.returncode == 0:
        return True
    last = ((r.stderr or r.stdout).strip().splitlines() or ["failed"])[-1]
    print(f"      WARN {' '.join(map(str, cmd[:4]))}: {last[:160]}")
    return False


def refresh(agent, st):
    _ver, mkt, ref, _local, _remote, _root = st
    row = next((m for m in b._marketplaces(agent) if m.get("name") == mkt), {})
    root = Path(row["root"]) if row.get("root") else None
    if agent == "claude" and root and (root / ".git").is_dir():
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                capture_output=True, text=True)
        if status.returncode != 0 or status.stdout.strip():
            print(f"      WARN claude marketplace {root} is dirty; commit it before update")
            return False
        branch = ref or subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        return invoke(["git", "-C", str(root), "pull", "--ff-only", "origin", branch])
    return invoke(b.AGENT_CLIS[agent]["refresh"](mkt))


print()
print("agents vs origin:")
failed = False
final = {}
for agent in agents:
    if not shutil.which(agent):
        print(f"   {agent:6}: no CLI on this machine")
        continue
    st = state(agent)
    if st is None:
        print(f"   {agent:6}: research-note NOT installed"
              f" — bootstrap_project.py installs it")
        continue
    show(agent, st)
    ver, mkt, ref, local, remote, root = st
    # A github-source marketplace is a tarball with no manifest to read; there
    # the running copy is the only answer available, so it stays the fallback.
    want = published(root) or running
    stale = ver != want or (local and remote and local != remote)
    if stale:
        print(f"      updating {agent} ...")
        if local and remote and local != remote:
            if not refresh(agent, st):
                failed = True
                continue
            # refresh() moved the marketplace clone forward, so the manifest
            # `want` was read from is now the OLD one. Re-read it, or the
            # install that follows is judged against a version that has just
            # been superseded and a correct update reports itself as a failure.
            want = published(root) or want
        if not invoke(b.AGENT_CLIS[agent]["update"](f"research-note@{mkt}")):
            failed = True
            continue
    st2 = state(agent) if not dry else st
    if st2:
        final[agent] = st2
        if not dry and st2[0] != want:
            print(f"      WARN {agent} resolved {st2[0]}, expected {want}")
            failed = True
        if stale and not dry:
            show(agent, st2)

if len(final) == 2:
    cv, xv = final["claude"], final["codex"]
    same_version = cv[0] == xv[0]
    same_commit = not (cv[3] and xv[3]) or cv[3] == xv[3]
    if same_version and same_commit:
        print("   parity: Claude and Codex resolve the same version and source commit")
    else:
        print("   WARN parity: Claude and Codex do not resolve the same package")
        failed = True

# Hand the resolved version back to the shell. The pluginRoot repoint in the
# project loop runs BEFORE this block and can only ever name the copy EXECUTING
# the script, so on the run that installs a new version it leaves every project
# pointing at the old one.
vers = {st[0] for st in final.values()}
if len(vers) == 1 and not dry and not failed:
    resolved_f.write_text(vers.pop())
raise SystemExit(1 if failed else 0)
PY
fi

# --- pluginRoot, corrected to the version the agents just RESOLVED to.
#
# The repoint inside the project loop can only name $CACHE — the copy executing
# this script — and that loop runs before the agents are updated. So on the one
# run that matters, the release run, every project is left pointing at the
# version being superseded. $PLUGIN in every skill, launcher, both linters, the
# record bus and the fixer's first branch resolves through this key, so the
# machine reports "updated" and goes on executing the old scripts.
#
# Measured, twice. 0.15.0 moved three scope pins while every $PLUGIN script kept
# running 0.14.2 — that is why the in-loop repoint exists at all. It was not
# enough: 0.29.1 then installed cleanly on both agents and all three projects
# kept executing 0.29.0's remote.sh, the single file that release existed to
# repair. The in-loop repoint stays as the `--agents none` path's answer; this
# pass is the one that can see what was installed.
if [ -s "$RESOLVED_F" ]; then
    RV=$(cat "$RESOLVED_F")
    # $CACHE is .../cache/<marketplace>/research-note/<version>, so its parent
    # holds the sibling version directories. Run out of a checkout instead and
    # that path does not exist, and the search below finds the real install.
    NEW_ROOT="$(dirname "$CACHE")/$RV"
    [ -d "$NEW_ROOT" ] || NEW_ROOT=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/"$RV" \
                                          "$HOME"/.codex/plugins/cache/*/research-note/"$RV" \
                                     2>/dev/null | head -1)
    if [ -n "$NEW_ROOT" ] && [ -d "$NEW_ROOT" ] && [ "$NEW_ROOT" != "$CACHE" ]; then
        MOVED=0
        for P in "${WANT[@]}"; do
            # A non-empty key is the mark of a project this run actually
            # handled; the loop above skips anything not on the framework, and
            # those must not be given one here.
            pr=$(git -C "$P" config --get research-note.pluginRoot 2>/dev/null)
            [ -n "${pr:-}" ] || continue
            [ "$pr" != "$NEW_ROOT" ] || continue
            [ "$MOVED" = 1 ] || echo ""
            git -C "$P" config research-note.pluginRoot "$NEW_ROOT"
            echo "   research-note.pluginRoot -> $RV   ($P, was $(basename "$pr"))"
            MOVED=1
        done
    fi
fi
rm -f "$RESOLVED_F"

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
    PREV=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/* \
                     "$HOME"/.codex/plugins/cache/*/research-note/* 2>/dev/null \
           | grep -Fvx "$CACHE" | sort -V | tail -1)
    if [ -n "$PREV" ] && [ "$PREV" != "$CACHE" ] && ! diff -q "$PREV/$f" "$CACHE/$f" >/dev/null 2>&1; then
        echo "   $CACHE/$f      (changed in $VER)"
    fi
done
echo "   plus any contract file listed as synced above (those cannot be reloaded at all)"

echo
if [ ${#CHANGED[@]} -gt 0 ]; then
    printf '%s\n' "${CHANGED[@]}" | sort -u | while read -r p; do
        echo "commit in $p:  git add .claude && git commit -m \"agent: update to research-note $VER\" -- .claude"
    done
    echo
    echo "Then, for a session to SEE the new skills: ask the user to run /reload-plugins."
    echo "Contract files cannot be reloaded — Read the ones listed as synced above."
else
    echo "nothing to sync — every project already on $VER"
fi

[ "$AGENT_SYNC_FAILED" = 0 ] || exit 1
