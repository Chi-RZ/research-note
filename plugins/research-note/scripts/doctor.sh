#!/usr/bin/env bash
# doctor.sh — check that this project's machinery is actually wired up, and say
# how to fix whatever is not. Run after bootstrap, after adding a remote, after
# a plugin update — and any time something behaves oddly.
#
# It is a re-runnable diagnosis, not a setup step, because most of what it
# catches was configured correctly once and drifted afterwards: a clone that
# predates the sparse default, a githook nobody installed, a fork checkout that
# moved past its pin, an environment that gained a package on one machine only.
#
# Usage: doctor.sh [--core] [--fixer] [--hpc [--host <h>]] [--editor] [--cross-agent]
#        (no flag: the core plus every integration the project enables)
# Exit:  0 all green · 1 at least one FAIL · 2 could not run
set -uo pipefail

PROJ="${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}"
while [ "$PROJ" != "/" ] && [ ! -f "$PROJ/.research-note/project.json" ] \
      && [ ! -f "$PROJ/.claude/framework.json" ]; do PROJ=$(dirname "$PROJ"); done
if [ ! -f "$PROJ/.research-note/project.json" ] && [ ! -f "$PROJ/.claude/framework.json" ]; then
    echo "doctor: not inside a framework project" >&2
    exit 2
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$PROJ/.claude/hpc.env" ] && . "$PROJ/.claude/hpc.env"
[ -f "$PROJ/.claude/hpc.local.env" ] && . "$PROJ/.claude/hpc.local.env"
. "$HERE/lib_paths.sh"

FAILED=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n     → %s\n' "$1" "$2"; }
bad()  { printf '  \033[31m✗\033[0m %s\n     → %s\n' "$1" "$2"; FAILED=1; }

echo "doctor: $PROJ"


# --- what to check. The CORE — plugin root, project configuration, record
# layer, git hooks, the project's own environment — is what every project has
# and is checked unless an integration is named alone. An INTEGRATION is
# checked when .research-note/project.json enables it (a project from before
# the declaration enables all four), or when it is named: a disabled one is
# neither started, required nor reported broken.
#   doctor.sh              core + every enabled integration
#   doctor.sh --core       core only
#   doctor.sh --fixer | --hpc [--host h] | --editor | --cross-agent
#                          that integration only, enabled or not (add --core to
#                          have the core as well)
RUN_CORE=1; CORE_FLAG=0; HOST_FILTER=""; declare -a ONLY=()
while [ $# -gt 0 ]; do
    case "$1" in
        --core) CORE_FLAG=1 ;;
        --all) ;;
        --fixer|--hpc|--editor|--cross-agent) ONLY+=("${1#--}") ;;
        --host) shift; HOST_FILTER=${1:-} ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "doctor: unknown argument $1 (--core, --fixer, --hpc, --editor, --cross-agent, --host h)" >&2; exit 2 ;;
    esac
    shift
done
[ ${#ONLY[@]} -gt 0 ] && [ "$CORE_FLAG" = 0 ] && RUN_CORE=0
feature_on() {  # feature_on <fixer|hpc|editor|cross_agent>
    if [ -f "$PROJ/.research-note/project.json" ]; then
        [ "$(python3 "$HERE/project_config.py" --project "$PROJ" feature "$1" 2>/dev/null)" = true ]
    else
        return 0
    fi
}
want() {  # want <feature>: named on the command line, or enabled and nothing was named
    local f=$1 o
    for o in ${ONLY[@]+"${ONLY[@]}"}; do [ "$o" = "${f//_/-}" ] && return 0; done
    [ ${#ONLY[@]} -gt 0 ] && return 1
    [ "$CORE_FLAG" = 1 ] && return 1
    feature_on "$f"
}
skipped() { printf '  \033[2m–\033[0m %s\n' "$1"; }
not_checked() {  # under the default run only: say that a disabled integration was left alone
    [ ${#ONLY[@]} -eq 0 ] && [ "$CORE_FLAG" = 0 ] \
        && skipped "$1: disabled in .research-note/project.json — not checked (doctor.sh --${1//_/-} to check it anyway)"
}

if [ "$RUN_CORE" = 1 ]; then
plugin_root=$(git -C "$PROJ" config --get research-note.pluginRoot 2>/dev/null)
if [ -n "$plugin_root" ] && [ -f "$plugin_root/.codex-plugin/plugin.json" ] \
        && [ -f "$plugin_root/.claude-plugin/plugin.json" ]; then
    ok "shared plugin root: $plugin_root"
else
    bad "shared plugin root is not configured" \
        "re-run bootstrap_project.py from the installed research-note plugin"
fi

EXPERIMENT_ROOTS=experiments
KNOWLEDGE_ROOTS=wiki
if [ -f "$PROJ/.research-note/project.json" ]; then
    if python3 "$HERE/project_config.py" --project "$PROJ" validate >/dev/null; then
        ok "project configuration is valid"
        # one line each: these go into messages and into a test built for ssh
        EXPERIMENT_ROOTS=$(printf '%s ' $(python3 "$HERE/project_config.py" --project "$PROJ" role experiments))
        KNOWLEDGE_ROOTS=$(printf '%s ' $(python3 "$HERE/project_config.py" --project "$PROJ" role knowledge))
        for role in libraries tests experiments knowledge; do
            roots=$(python3 "$HERE/project_config.py" --project "$PROJ" role "$role")
            for root in $roots; do
                [ -d "$PROJ/$root" ] && ok "$role root: $root/" \
                  || bad "$role root is missing: $root/" "create it or correct .research-note/project.json"
            done
        done
        # Every top-level directory belongs to a layer, or is ignored. Nothing
        # enforced this until the first commit touching an unowned folder,
        # which is refused under every prefix — months after setup, and far
        # from the declaration that would have prevented it.
        owned=$(python3 - "$PROJ" <<'PY'
import json, sys
from pathlib import Path
cfg = json.loads((Path(sys.argv[1]) / ".research-note/project.json").read_text())
print("\n".join(sorted({p for l in cfg["layers"].values() for p in l["paths"]})))
PY
)
        unowned=""
        for d in "$PROJ"/*/; do
            [ -d "$d" ] || continue
            b=$(basename "$d")
            printf '%s\n' "$owned" | grep -qx "$b" && continue
            git -C "$PROJ" check-ignore -q "$b" 2>/dev/null && continue
            unowned="$unowned $b"
        done
        if [ -z "${unowned# }" ]; then
            ok "every top-level directory belongs to a layer"
        else
            warn "no layer owns:$unowned" \
                 "a commit touching one is refused under EVERY prefix — give each its own layer in .research-note/project.json, move it under a declared root, or .gitignore it"
        fi
    else
        bad "project configuration is invalid" \
            "python3 $HERE/project_config.py --project $PROJ validate"
    fi
else
    warn "legacy project has no .research-note/project.json" \
         "re-run bootstrap_project.py once to record its layout and enabled integrations"
fi

echo
echo "record layer"
main_root="$(dirname "$(git -C "$PROJ" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")"
if [ "$main_root" = "$PROJ" ]; then ok "running from the main checkout"
else warn "this is a linked worktree (main is $main_root)" \
          "records belong to the main checkout; the bus writes there regardless"; fi
def="$(git -C "$PROJ" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
# no origin yet: the same fallback the record bus uses, so the two agree on
# which branch the record lives on — main if it exists, else master
if [ -z "$def" ]; then
    if git -C "$main_root" show-ref -q --verify refs/heads/main; then def=main
    elif git -C "$main_root" show-ref -q --verify refs/heads/master; then def=master
    else def=main; fi
fi
# symbolic-ref first: it answers on an UNBORN branch, where rev-parse says
# "HEAD" and the check then reported a fresh `git init` as being on the wrong
# branch — the state every new project is in between bootstrap and its first
# commit. It returns non-zero on a genuinely detached HEAD, which is what the
# rev-parse fallback is for.
cur="$(git -C "$main_root" symbolic-ref -q --short HEAD 2>/dev/null)" \
  || cur="$(git -C "$main_root" rev-parse --abbrev-ref HEAD 2>/dev/null)"
if ! git -C "$main_root" rev-parse -q --verify HEAD >/dev/null 2>&1; then
    ok "main checkout on $cur (no commits yet — the first commit settles the record branch)"
elif [ "$cur" = "$def" ]; then
    ok "main checkout on $def"
else
    bad "main checkout is on '$cur', not '$def'" "the bus refuses to write the record off the default branch"
fi
# The hook layout is the install module's to know: the dispatcher, research-note's
# own checks under it, one link per hook name, and the previous hook directory
# every event is forwarded to. It reports what is missing and the one command
# that lays it.
if [ -f "$HERE/githooks_install.py" ]; then
    while IFS="$(printf '\t')" read -r level message fix; do
        [ -n "$level" ] || continue
        case "$level" in
            OK)   ok "$message" ;;
            WARN) warn "$message" "$fix" ;;
            *)    bad "$message" "$fix" ;;
        esac
    done <<EOF_HOOKS
$(python3 "$HERE/githooks_install.py" status "$PROJ" 2>/dev/null)
EOF_HOOKS
else
    hp="$(git -C "$PROJ" config core.hooksPath)"
    [ -n "$hp" ] && ok "githooks installed (core.hooksPath=$hp)" \
      || bad "core.hooksPath unset" "re-run bootstrap_project.py"
fi

dirty=$(git -C "$PROJ" status --porcelain -- project_memory 2>/dev/null | grep -c '\.md$')
[ "${dirty:-0}" -eq 0 ] && ok "no uncommitted record edits" \
  || warn "$dirty record file(s) uncommitted" "the bus commits what it writes — these came from somewhere else; commit them yourself"
# a failed bus push is a one-line warning at commit time and silent after —
# committed-but-unpushed record accumulates invisibly until something reads it
if git -C "$main_root" remote get-url origin >/dev/null 2>&1; then
    ahead=$(git -C "$main_root" rev-list --count '@{upstream}..HEAD' 2>/dev/null)
    if [ -z "$ahead" ]; then
        warn "the default branch has no upstream" "git -C $main_root push -u origin $cur"
    elif [ "$ahead" -eq 0 ]; then ok "no unpushed commits"
    else warn "$ahead unpushed commit(s) — a bus push failed, or never ran" "git -C $main_root push"; fi
fi

if command -v uv >/dev/null 2>&1; then ok "uv on PATH"
else bad "no uv on PATH" "the launchers and the bus both shell out to it"; fi
if command -v python3 >/dev/null 2>&1; then ok "python3 available (the record lock, the linters)"
else bad "no python3" "the bus cannot lock, hash or lint the record without it"; fi
# core runtime state — the record lock, the harvest stamps — outside .fixer/,
# so a project without a fixer still has somewhere to lock
if mkdir -p "$PROJ/.research-note/state" 2>/dev/null; then
    if git -C "$PROJ" check-ignore -q .research-note/state/record.lock 2>/dev/null; then
        ok "core state dir .research-note/state/ (gitignored)"
    else warn "core state dir .research-note/state/ is not gitignored" \
              "printf 'state/\\n' > $PROJ/.research-note/.gitignore — or the record lock ends up in a commit"; fi
else bad "cannot create .research-note/state/" "the record bus and the launcher lock there"; fi
echo
echo "python environment"
if [ -x "$PROJ/.venv/bin/python" ]; then
    ok "venv $("$PROJ/.venv/bin/python" -V 2>&1 | tr -d '\n')"
else bad "no .venv" "uv sync"; fi
if grep -q 'git = ' "$PROJ/pyproject.toml" 2>/dev/null; then
    bl_out=$(bash "$HERE/bump_lib.sh" --check 2>&1); bl_rc=$?
    if [ "$bl_rc" = 0 ]; then ok "fork pins current"
    elif printf '%s' "$bl_out" | grep -q "no checkout known"; then
        # Distinct fault, distinct fix: bump_lib exits non-zero both for real
        # drift and for a checkout it cannot locate, and telling the user to run
        # --all in the second case just fails again.
        bad "a pinned fork's checkout is not declared" "add it to LIB_CHECKOUTS in .claude/hpc.env — $(printf '%s' "$bl_out" | head -1)"
    else bad "a fork checkout has moved past its pin" "bump_lib.sh --all, then commit pyproject.toml + uv.lock"; fi
elif [ -n "$(lib_names)" ]; then
    for name in $(lib_names); do
        lp=$(lib_path_for "$name" LOCAL)
        if [ -z "$lp" ]; then
            bad "lib $name declares no LIB_${name}_LOCAL" "add the local checkout path to .claude/hpc.env"
        elif git -C "$lp" rev-parse --git-dir >/dev/null 2>&1; then ok "lib $name at $lp"
        else bad "LIB_${name}_LOCAL=$lp is not inside a git checkout" "clone it there, or fix the path"; fi
        if [ -n "${REMOTE_HOST:-}" ]; then
            hk=$(lib_hostkey "$REMOTE_HOST")
            [ -n "$(lib_path_for "$name" "$hk")" ] || \
                bad "lib $name has no LIB_${name}_${hk} path for $REMOTE_HOST" \
                    "declare the remote checkout path — remote.sh push refuses without it"
        fi
    done
elif [ -n "${SYNC_LIBS:-}" ]; then
    for lib in $SYNC_LIBS; do
        [ -d "$lib/.git" ] && ok "editable lib $(basename "$lib") at $lib (legacy SYNC_LIBS — migrate to LIB_<name>_<side> lines)" \
          || bad "SYNC_LIBS names $lib, which is not a git checkout" "clone it there, or pin the fork by commit instead"
    done
fi

if [ -n "${JULIA_PROJECT:-}" ]; then
    echo
    echo "julia environment"
    if command -v julia >/dev/null 2>&1 && [ -f "$PROJ/$JULIA_PROJECT/Manifest.toml" ]; then
        jm=$(cd "$PROJ/$JULIA_PROJECT" && julia --project=. -e 'using Pkg; d=Pkg.dependencies(); m=[p.name for (u,p) in d if p.source===nothing || !isdir(p.source)]; isempty(m) ? println("ok ", length(d)) : println("missing ", join(m,","))' 2>/dev/null | tail -1)
        case "$jm" in
            ok\ *) ok "$JULIA_PROJECT instantiated (${jm#ok } packages)" ;;
            missing\ *) bad "$JULIA_PROJECT does not match its Manifest — ${jm#missing }" \
                            "cd $JULIA_PROJECT && julia --project=. -e 'using Pkg; Pkg.instantiate()'" ;;
            *) warn "cannot verify $JULIA_PROJECT" "julia ran but said nothing readable — check it by hand" ;;
        esac
    elif [ ! -f "$PROJ/$JULIA_PROJECT/Manifest.toml" ]; then
        bad "JULIA_PROJECT names $JULIA_PROJECT, which holds no Manifest.toml" "point it at the env directory, repo-relative"
    else warn "cannot verify $JULIA_PROJECT — no julia on PATH here" "install julia, or drop JULIA_PROJECT if this machine never runs it"; fi
    # A SECOND environment is allowed — one platform-only dependency (MKL has no
    # aarch64 build) is enough to make a single file unusable somewhere. What is
    # not allowed is the two drifting apart underneath that difference, so the
    # rule is containment: every package of the base must appear in the variant
    # AT THE SAME VERSION, and the variant may only add. Pure file-vs-file, in
    # git, no host involved.
    if [ -n "${JULIA_PROJECT_VARIANTS:-}" ]; then
        VM=""; for VAR in $JULIA_PROJECT_VARIANTS; do VM="$VM $PROJ/$VAR/Manifest.toml"; done
        python3 "$HERE/julia_variants.py" "$PROJ/$JULIA_PROJECT/Manifest.toml" $VM || FAILED=1
    fi
fi

fi

if want hpc; then
[ -f "$PROJ/.claude/hpc.env" ] && ok "hpc profile .claude/hpc.env" \
  || bad "hpc: .claude/hpc.env is missing" "re-run bootstrap_project.py --with-hpc"
echo
echo "local launch venue"
if command -v sbatch >/dev/null 2>&1; then
    ok "local Slurm (submit_slurm.sh; submit files under $EXPERIMENT_ROOTS/<node>/<group>/submit/)"
    [ -n "${REMOTE_PARTITION:-}${REMOTE_RESERVATION:-}${REMOTE_ACCOUNT:-}" ] \
      && ok "queue placement declared" \
      || warn "no queue placement for the LOCAL cluster" \
              "jobs land in its default queue — REMOTE_PARTITION / REMOTE_RESERVATION / REMOTE_ACCOUNT in .claude/hpc.env"
else
    ok "local bare host (launch_bare_gpu.sh; jobs are wrapper PIDs)"
fi

for RH in ${HOST_FILTER:-${REMOTE_HOSTS:-${REMOTE_HOST:-}}}; do
    v="REMOTE_DIR_$(printf '%s' "$RH" | tr -c 'A-Za-z0-9_' '_')"
    RD="${!v:-${REMOTE_DIR:-}}"
    echo
    echo "remote: $RH"
    if ! ssh -o BatchMode=yes -o LogLevel=ERROR -o ConnectTimeout=10 "$RH" true 2>/dev/null; then
        bad "cannot ssh" "check ~/.ssh/config and that the key is authorized; everything below is skipped"
        continue
    fi
    ok "ssh reachable"
    [ -n "$RD" ] || { bad "no clone path declared" "add REMOTE_DIR_$RH=<path> to .claude/hpc.env"; continue; }
    if ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "test -d '$RD/.git'" 2>/dev/null; then ok "clone at $RD"
    else bad "no clone at $RD" "remote.sh setup --host $RH"; fi
    # Ask the WORKING TREE, not the porcelain. `git sparse-checkout` arrived in
    # 2.25 and cluster git is routinely 1.8, where the subcommand is missing and
    # the probe failed unconditionally — reporting a stale record copy on hosts
    # that carried none, twice sending a session to investigate nothing. What the
    # check is actually about is whether the record is materialised there, so it
    # looks: the directory's absence IS the answer, on every git ever shipped.
    sparse_test="test ! -e '$RD/project_memory'"
    for root in $KNOWLEDGE_ROOTS; do sparse_test="$sparse_test && test ! -e '$RD/$root'"; done
    if ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "$sparse_test" 2>/dev/null; then
        ok "sparse (no record copy on the cluster)"
    else warn "the clone carries a record copy — project_memory/ or $KNOWLEDGE_ROOTS is materialised on $RH" \
              "a stale record on a cluster is a page someone eventually reads and believes; remote.sh setup --host $RH excludes both and keeps everything else"; fi
    sched=$(ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" 'command -v sbatch >/dev/null && echo slurm || { command -v qsub >/dev/null && echo pbs || { command -v bsub >/dev/null && echo lsf || echo bare; }; }' 2>/dev/null)
    case "$sched" in
        slurm) ok "scheduler: Slurm (submit files under $EXPERIMENT_ROOTS/<node>/<group>/submit/)" ;;
        bare)  ok "scheduler: none — bare remote (remote.sh submit ships the launcher)" ;;
        *)     bad "scheduler: $sched — not supported" "only Slurm and bare remotes have a submit path; remote.sh would fail" ;;
    esac
    if [ "$sched" = slurm ] && [ -z "${REMOTE_PARTITION:-}${REMOTE_RESERVATION:-}${REMOTE_ACCOUNT:-}" ]; then
        warn "no partition/reservation/account declared for $RH" \
             "jobs land in the cluster default queue — add REMOTE_PARTITION / REMOTE_RESERVATION / REMOTE_ACCOUNT to .claude/hpc.env (blank is fine if this cluster needs none)"
    fi
    if ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "test -x '$RD/.venv/bin/python'" 2>/dev/null; then
        rv=$(ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "'$RD/.venv/bin/python' -V 2>&1" | tr -d '\r\n')
        lv=$("$PROJ/.venv/bin/python" -V 2>&1 | tr -d '\n')
        lmm=$(printf '%s' "$lv" | grep -oE '[0-9]+\.[0-9]+'); rmm=$(printf '%s' "$rv" | grep -oE '[0-9]+\.[0-9]+')
        if [ "$rv" = "$lv" ]; then ok "python matches ($rv)"
        elif [ "$lmm" = "$rmm" ]; then
            # Same minor = same ABI and the same wheels; the patch digit is what
            # each host last downloaded. Worth knowing, not worth chasing.
            ok "python $lmm on both (patch differs: local $lv, $RH $rv)"
        else
            bad "python MINOR differs — local $lv, $RH $rv" \
                "different ABI, different wheels, compiled extensions built differently: pin requires-python to one minor (e.g. >=3.12,<3.13) and rebuild the remote venv"
        fi
        # Measured against the LOCKFILE, on the machine that will run the job —
        # not against this laptop. One lock resolves to a different installed set
        # per platform (a Mac gets no nvidia-* wheels, and the lock's markers say
        # so), so comparing the two machines was permanently red on a Mac/Linux
        # pair while both were exactly right. rc 3 = no uv there, a different
        # answer from "the venv is wrong".
        envout=$(ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "bash -lc 'command -v uv >/dev/null || exit 3; cd \"$RD\" && uv sync --check'" 2>&1); envrc=$?
        case "$envrc" in
            0) ok "remote venv matches uv.lock" ;;
            3) warn "no uv on $RH — its venv cannot be checked against uv.lock" \
                    "install uv there (curl -LsSf https://astral.sh/uv/install.sh | sh)" ;;
            *) bad "remote venv does not match uv.lock — $(printf '%s' "$envout" | tail -1)" \
                   "ssh $RH 'cd $RD && uv sync' (login node is fine — it is not compute)" ;;
        esac
    else bad "no .venv at $RD" "ssh $RH 'cd $RD && uv sync' (login node is fine — it is not compute)"; fi
    # An editable dependency's identity is its commit, and no venv check can see
    # it: uv verifies the LINK, never what the checkout holds. A declared lib
    # (LIB_<name>_LOCAL / LIB_<name>_<HOSTKEY>) is compared side to side here;
    # pinning by rev in the lockfile settles it for good instead.
    hk=$(lib_hostkey "$RH")
    for name in $(lib_names); do
        lp=$(lib_path_for "$name" LOCAL); rp=$(lib_path_for "$name" "$hk")
        [ -n "$lp" ] && [ -n "$rp" ] || continue   # the local block already flagged a missing side
        rsha=$(ssh -o BatchMode=yes -o LogLevel=ERROR "$RH" "git -C '$rp' rev-parse HEAD" 2>/dev/null)
        lsha=$(git -C "$lp" rev-parse HEAD 2>/dev/null)
        if [ -z "$rsha" ]; then
            bad "lib $name: no git checkout at $RH:$rp" "clone it there, or fix LIB_${name}_${hk}"
        elif [ "$rsha" = "$lsha" ]; then ok "lib $name @ $(printf %.7s "$lsha") on both sides"
        else bad "lib $name diverges — local $(printf %.7s "$lsha") vs $RH $(printf %.7s "$rsha")" \
                 "remote.sh push aligns it (fetch + ff on the remote); run it, or reconcile by hand"; fi
    done
    # Legacy shapes: recorded but unheld — the exact hole the LIB_* scheme closes.
    if [ -z "$(lib_names)" ] && [ -n "${DOMAIN_LIBS:-${DOMAIN_LIB_DIR:-}}" ]; then
        warn "an editable lib's commit is recorded but nothing holds the two sides to it" \
             "declare LIB_<name>_LOCAL and LIB_<name>_${hk} in .claude/hpc.env (record + push gate together), or pin the fork by rev — { git = ..., rev = <sha> }, bump_lib.sh to move it"
    fi
done
else not_checked hpc; fi

if want fixer; then
echo
echo "background scanner"
hb="$PROJ/.fixer/last_run"
if [ -f "$hb" ]; then
    age=$(( ( $(date +%s) - $(date -r "$hb" +%s 2>/dev/null || echo 0) ) / 60 ))
    [ "$age" -lt 30 ] && ok "fixer alive (last cycle ${age} min ago)" \
      || bad "fixer heartbeat ${age} min old" "cron or the daemon died — $PROJ/.fixer/run.sh, and see .fixer/last_error"
else
    warn "fixer never ran" "fixer/start_fixer_daemon.sh — without it nothing raises a hand when a loop dies unattended"
fi
if [ -s "$PROJ/.fixer/last_error" ]; then
    bad "fixer reported an error" "$(head -c 160 "$PROJ/.fixer/last_error")"
else ok "no fixer errors"; fi
# The scanner's whole job is to surface things; a stale queue snapshot means
# its remote view — and every J3 on a remote job — is blind.
snap="$PROJ/.fixer/remote_queue"
if [ -n "${REMOTE_HOST:-}${REMOTE_HOSTS:-}" ]; then
    if [ -f "$snap" ]; then
        sage=$(( ( $(date +%s) - $(date -r "$snap" +%s 2>/dev/null || echo 0) ) / 60 ))
        [ "$sage" -lt 30 ] && ok "remote queue snapshot ${sage} min old" \
          || warn "remote queue snapshot ${sage} min old" "remote.sh queue — until then J3 cannot judge a remote job"
    else warn "no remote queue snapshot yet" "remote.sh queue"; fi
fi
else not_checked fixer; fi

if want editor; then
echo
echo "editor support"
ext_seen=0
for ext_dir in "$HOME/.vscode-server/extensions" "$HOME/.vscode/extensions"; do
    [ -d "$ext_dir" ] || continue
    ext_seen=1
    if [ -d "$ext_dir/local.qdash-0.0.1" ]; then ok "qdash board viewer in $ext_dir"
    else bad "qdash board viewer missing from $ext_dir" "re-run bootstrap_project.py --with-editor, then Reload Window"; fi
done
[ "$ext_seen" = 1 ] || warn "no VS Code extensions directory on this machine" \
    "nothing to install into — the board is still readable as project_memory/dashboard.html"
else not_checked editor; fi

if want cross_agent; then
echo
echo "the other agent"
agents_seen=0
if command -v codex >/dev/null 2>&1; then
    agents_seen=1
    if grep -q 'research-note@' "$HOME/.codex/config.toml" 2>/dev/null; then ok "codex has the plugin registered"
    else bad "codex is installed but has no research-note plugin" "re-run bootstrap_project.py --with-cross-agent from the Claude cache, or codex plugin add"; fi
fi
if command -v claude >/dev/null 2>&1; then
    agents_seen=1
    if grep -q 'research-note@' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null; then ok "claude has the plugin registered"
    else bad "claude is installed but has no research-note plugin" "re-run bootstrap_project.py --with-cross-agent from the Codex cache, or claude plugin install"; fi
fi
[ "$agents_seen" = 1 ] || warn "neither claude nor codex is on PATH" "nothing to register the plugin with"
else not_checked cross_agent; fi

echo
[ "$FAILED" = 0 ] && echo "doctor: all green" || echo "doctor: fix the ✗ items above"
exit "$FAILED"
