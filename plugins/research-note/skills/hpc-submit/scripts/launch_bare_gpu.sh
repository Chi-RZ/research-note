#!/bin/bash
# Background-launch ONE Python job on a bare GPU/CPU server (no Slurm).
# Writes the standard log header (git SHAs + scoped dirty diff), exports the
# JAX GPU environment, launches detached, records the wrapper + payload PIDs
# in the header, and flips "# Exit code" in the log when the job ends.
# Canonical job id = the WRAPPER PID: known at fork time, spans the whole job
# lifecycle (it waits on the payload and flips the exit code), and is
# payload-agnostic. Invoked directly (no copy, no placeholders); the agent
# loops over calls for sweeps (SKILL.md Case B).
#
# Usage: launch_bare_gpu.sh <script.py> <gpu_id|cpu> <mem_frac> [args...]
#   <gpu_id|cpu>  GPU index (exported as GPU_ID), or "cpu" to hide all GPUs
#   <mem_frac>    XLA_PYTHON_CLIENT_MEM_FRACTION / MEM_FRAC (ignored for cpu)
#   [args...]     forwarded verbatim to the python script
# Env: TAG=<key_params>    appended to the log stem (e.g. TAG=D64)
#      CONFIG=<yaml path>  channel-1 (Hydra pipeline) scripts only: freeze the
#                          draft config for this run — copied to
#                          logs/<stem>.yaml and the job reads THAT copy via
#                          Hydra's -cp/-cn (never the live file, which stays
#                          free to edit for the next run)
#      RUNNER=<cmd>        payload command, word-split, prepended to
#                          <script.py> (default: "uv run python -u")
# Output: progress lines; the LAST line is the wrapper PID (canonical job
# id, the liveness handle).

set -uo pipefail

# Developed libraries come from <project>/.research-note/editables.env (sourced
# after REPO_ROOT is known) as LIB_<name>_LOCAL / LIB_<name>_<HOSTKEY> lines.
# sync_editables creates a project-local slot on each machine; this launcher
# discovers that slot without needing the private path map on the cluster
# (contract: templates/editables.env; canonical functions: scripts/lib_paths.sh,
# copied here because this file travels alone). A declared lib that resolves
# nowhere
# writes a WARNING line into the header rather than vanishing: the silent skip
# is how eight runs got recorded against a commit no remote holds. Legacy
# spellings DOMAIN_LIBS / DOMAIN_LIB_DIR are honoured when no LIB_* is
# declared.

# >>> lib_paths (keep every copy of this block identical) >>>
lib_slot_root() {
    local root=${REPO_ROOT:-}
    [ -n "$root" ] || root=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
    printf '%s\n' "$root/.research-note/editables"
}
lib_names() {  # every declared <name>, once, one per line
    local v n p root seen=" "
    root=$(lib_slot_root 2>/dev/null) || root=""
    if [ -n "$root" ]; then
        for p in "$root"/*; do
            [ -d "$p" ] || continue
            n=$(basename "$p")
            case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
        done
    fi
    for v in "${!LIB_@}"; do
        n=${v#LIB_}; n=${n%_*}
        case "$n" in CHECKOUTS) continue ;; esac   # legacy bump_lib map, not a lib
        case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
    done
}
lib_path_here() {  # <name> -> the first declared path that exists on THIS machine
    local v suffix root
    root=$(lib_slot_root 2>/dev/null) || root=""
    [ -n "$root" ] && [ -d "$root/$1" ] && { printf '%s\n' "$root/$1"; return 0; }
    for v in "${!LIB_@}"; do
        case "$v" in "LIB_$1_"*) ;; *) continue ;; esac
        suffix=${v#LIB_$1_}
        case "$suffix" in *_*) continue ;; esac   # a longer lib name, not a side of this one
        [ -d "${!v}" ] && { printf '%s\n' "${!v}"; return 0; }
    done
    return 1
}
lib_path_for() {  # <name> <side: LOCAL or a hostkey> -> the declared path, set or fail
    local v="LIB_$1_$2"
    [ -n "${!v:-}" ] && printf '%s\n' "${!v}"
}
lib_hostkey() {  # <host> -> its variable-suffix spelling (alphanumerics only)
    local h=$1 out="" c
    while [ -n "$h" ]; do
        c=${h%"${h#?}"}; h=${h#?}
        case "$c" in [A-Za-z0-9]) out="$out$c" ;; esac
    done
    printf '%s\n' "$out"
}
# <<< lib_paths <<<

[ "$#" -ge 3 ] || { echo "Usage: $0 <script.py> <gpu_id|cpu> <mem_frac> [args...]" >&2; exit 1; }

# Every launch must name the entry it belongs to, so the job id + log land on the
# task page at submit time (see the record step at the bottom). Refusing here is the
# point: an unrecorded short job is invisible forever — it starts and ends between
# two polling snapshots, so no later check can recover it.
: "${ENTRY:?ENTRY is required — set ENTRY=\"peps_sma/heis_tri: peps_sma vs ED on heis_tri 4x4\" (<node>/<page>: entry name). Every launch through this script is a RECORDED run — an unrecorded probe is a <30 min foreground `uv run`, not a background launch. ENTRY=none exists for remote.sh, which ships this launcher to a sparse clone with no record layer, and records on the local side instead.}"
PY_SRC=$1; DEVICE=$2; FRAC=$3; shift 3
[ -f "$PY_SRC" ] || { echo "script not found: $PY_SRC" >&2; exit 1; }
PY_ABS=$(cd "$(dirname "$PY_SRC")" && pwd)/$(basename "$PY_SRC")
REPO_ROOT=$(git -C "$(dirname "$PY_ABS")" rev-parse --show-toplevel)
# The project's declared environment (.research-note/project.json): which tool
# locks it, and how a recorded run invokes Python. Read inline, not through
# the plugin's project_config.py, because this script travels to a cluster
# alone. No declaration means a project from before it: uv, as it always was.
rn_read_env() {
    python3 - "$1/.research-note/project.json" <<'PYENV' 2>/dev/null
import json, sys
try:
    env = json.load(open(sys.argv[1])).get("environment", {})
except Exception:
    env = {}
manager = env.get("manager", "uv")
print(manager)
print(env.get("runner") or ("uv run --no-sync python -u" if manager == "uv" else "python -u"))
PYENV
}
ENV_DECL=$(rn_read_env "$REPO_ROOT")
ENV_MANAGER=$(printf '%s\n' "$ENV_DECL" | sed -n 1p); ENV_MANAGER=${ENV_MANAGER:-uv}
# an explicit RUNNER still wins: it is how a one-off run overrides the project
[ -n "${RUNNER:-}" ] || RUNNER=$(printf '%s\n' "$ENV_DECL" | sed -n 2p)
RUNNER=${RUNNER:-uv run --no-sync python -u}
# A recorded run's evidence must outlive its checkout: a linked worktree is
# removed when its session ends, leaving the entry's log link dangling on a
# page that lives forever. Smoke (ENTRY=none) stays legal anywhere.
if [ "$ENTRY" != none ] && [ "$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-dir)" \
        != "$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)" ]; then
    echo "launch_bare_gpu: formal runs launch from main — this is a linked WORKTREE, and its logs die with it. ENTRY=none for a smoke, or launch from the main checkout." >&2; exit 1
fi
[ -f "$REPO_ROOT/.claude/hpc.env" ] && . "$REPO_ROOT/.claude/hpc.env"
[ -f "$REPO_ROOT/.claude/hpc.local.env" ] && . "$REPO_ROOT/.claude/hpc.local.env"
[ -f "$REPO_ROOT/.research-note/editables.env" ] && . "$REPO_ROOT/.research-note/editables.env"
# experiment dir = parent of scripts/, else the script's own dir
d=$(dirname "$PY_ABS")
if [ "$(basename "$d")" = scripts ]; then EXP_DIR=$(dirname "$d"); else EXP_DIR=$d; fi
mkdir -p "$EXP_DIR/logs"

# Pre-flight the record BEFORE anything launches: resolve the page and the
# entry now, so a typo'd ENTRY aborts with nothing running — found after the
# fact it costs a live job whose record failed, behind an exit 3 no retry may
# follow. record_submit.py is framework code living in the plugin's scripts/;
# resolve by probing beside this script, then fall back to the installed
# plugin (same pick as the record step below; absent on a sparse remote clone,
# where ENTRY=none skips all of this).
SD=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REC=""
for cand in "$SD/../../../scripts" "$SD/../scripts" "$SD"; do
    [ -f "$cand/record_submit.py" ] && { REC="$cand/record_submit.py"; break; }
done
SELECTED_PLUGIN=$(git config --get research-note.pluginRoot 2>/dev/null || true)
[ -n "$REC" ] || { [ -f "$SELECTED_PLUGIN/scripts/record_submit.py" ] && REC="$SELECTED_PLUGIN/scripts/record_submit.py"; }
PAGE=""; ENTRY_NAME=""
# The phase this launch serves. A launch comes FROM a phase — the Plan is what
# said to run this — so the binding is known here and nowhere later: the entry
# line used to be left to a turn after the launch, and a job that runs for
# hours reliably swallows that turn. record_submit writes the line; PHASE and
# ROLE are the two things only this session knows. NO_OBJECTIVE=1 for a run
# that serves no phase.
BIND=()
[ -n "${PHASE:-}" ] && BIND+=(--phase "$PHASE")
[ -n "${ROLE:-}" ]  && BIND+=(--role "$ROLE")
[ "${NO_OBJECTIVE:-0}" = 1 ] && BIND+=(--no-objective)
if [ "$ENTRY" != none ]; then
    PAGE=${ENTRY%%:*}
    ENTRY_NAME=${ENTRY#*:}
    ENTRY_NAME=${ENTRY_NAME# }
    if [ -n "$REC" ]; then
        python3 "$REC" --check "$PAGE" "$ENTRY_NAME" ${BIND[@]+"${BIND[@]}"} >&2 \
            || { echo "pre-flight failed — fix ENTRY (\"$ENTRY\") or create the entry first; NOTHING was launched" >&2; exit 1; }
    fi
fi

TS=$(date +%Y%m%d-%H%M%S)
STEM="$(basename "$PY_SRC" .py)${TAG:+-$TAG}-$TS"
LOG="$EXP_DIR/logs/$STEM.log"

FROZEN=""
if [ -n "${CONFIG:-}" ]; then
    [ -f "$CONFIG" ] || { echo "config not found: $CONFIG" >&2; exit 1; }
    FROZEN="$EXP_DIR/logs/$STEM.yaml"
    cp "$CONFIG" "$FROZEN"
    set -- "$@" -cp "$EXP_DIR/logs" -cn "$STEM"
fi

if [ "$DEVICE" = cpu ]; then
    ENVS=(CUDA_VISIBLE_DEVICES=)
else
    # PCI_BUS_ID: make CUDA enumeration match nvidia-smi indices (default
    # FASTEST_FIRST silently remaps multi-GPU id lists, e.g. picks the DGX
    # Display card)
    ENVS=(GPU_ID="$DEVICE" CUDA_DEVICE_ORDER=PCI_BUS_ID XLA_PYTHON_CLIENT_MEM_FRACTION="$FRAC" MEM_FRAC="$FRAC")
fi
# JAX GPU environment (SKILL.md General rules)
ENVS+=("XLA_FLAGS=--xla_gpu_shard_autotuning=false --xla_gpu_experimental_enable_fusion_autotuner=false --xla_gpu_enable_triton_gemm=false"
       JAX_COMPILATION_CACHE_DIR="$HOME/jax_cache"
       JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS=10)

dirty() { [ -z "$(git -C "$1" status --porcelain)" ] && echo clean || echo dirty; }

# PID fields are fixed-width placeholders, patched in place after launch with
# dd conv=notrunc — sed -i would swap the inode and orphan the running job's
# open fd, silently losing all its subsequent output.
{
    echo "# Command: ${ENVS[*]} $RUNNER $PY_SRC $*"
    echo "# Cwd: $PWD"
    echo "# Timestamp: $(date +%Y-%m-%dT%H:%M:%S%z)"
    echo "# $(basename "$REPO_ROOT"): $(git -C "$REPO_ROOT" rev-parse --short HEAD) ($(dirty "$REPO_ROOT"))"
    LIB_DECLARED=$(lib_names)
    for name in $LIB_DECLARED; do
        if p=$(lib_path_here "$name"); then
            if lib_sha=$(git -C "$p" rev-parse --short HEAD 2>/dev/null); then
                echo "# $name: $lib_sha ($(dirty "$p"))"
            else
                echo "# $name: WARNING not a git checkout ($p)"
            fi
        else
            echo "# $name: WARNING declared in editables.env but no LIB_${name}_* path exists on this machine"
        fi
    done
    # Legacy spellings, honoured only when nothing is declared the new way —
    # and a dead path now says so in the header instead of vanishing.
    [ -z "$LIB_DECLARED" ] && for lib in ${DOMAIN_LIBS:-${DOMAIN_LIB_DIR:-}}; do
        if lib_sha=$(git -C "$lib" rev-parse --short HEAD 2>/dev/null); then
            echo "# $(basename "$lib"): $lib_sha ($(dirty "$lib"))"
        else
            echo "# $(basename "$lib"): WARNING path does not resolve on this machine ($lib)"
        fi
    done
    echo "# Config: ${FROZEN:-none}"
    if [ "$ENV_MANAGER" = uv ]; then
        echo "# Environment: locked by uv.lock"
    else
        echo "# Environment: NOT locked — environment.manager is \"$ENV_MANAGER\"; this run records its environment, but nothing guarantees it can be rebuilt"
    fi
    # Pinned fork revisions (from uv.lock) + installed-package fingerprint
    # (see the .slurm templates for the rationale).
    [ -x "$REPO_ROOT/.venv/bin/python" ] && "$REPO_ROOT/.venv/bin/python" - "$REPO_ROOT" <<'PYFP' 2>/dev/null
import hashlib, json, re, sys
from importlib.metadata import distributions
from pathlib import Path

# Git-pinned sources are what actually RUNS when a project pins its forks by
# commit: the lockfile is the truth, not any working checkout, which may have
# moved on without a bump. (Path-editable projects print checkout SHAs from the
# DOMAIN_LIBS loop above instead.)
lock = Path(sys.argv[1] if len(sys.argv) > 1 else ".") / "uv.lock"
if lock.exists():
    for m in re.finditer(
            r'name = "([^"]+)"\nversion = "[^"]*"\nsource = \{ git = "[^"?]+\?rev=([0-9a-f]+)',
            lock.read_text()):
        print(f"# {m.group(1)}: {m.group(2)[:8]} (pinned)")

# Installed package set — the SHAs pin the SOURCE, this pins what is installed
# AROUND it: an optional accelerator present on one machine only sends the same
# code down a different route, and no SHA sees it. Editables are skipped: their
# recorded version goes stale by design.
r = []
for d in distributions():
    n = (d.metadata["Name"] or "").lower()
    if not n:
        continue
    try:
        u = d.read_text("direct_url.json")
        if u and json.loads(u).get("dir_info", {}).get("editable"):
            continue
    except Exception:
        pass
    r.append(f"{n}=={d.version}")
r = sorted(set(r))
print(f"# env: {len(r)} {hashlib.sha256(chr(10).join(r).encode()).hexdigest()[:16]}")
PYFP
    # PID fields are fixed-width placeholders, patched in place after launch with
    # dd conv=notrunc — sed -i would swap the inode and orphan the running job's
    # open fd, silently losing all its subsequent output. The wrapper PID is the
    # canonical job id; the liveness readers (check_node_page.py, remote.sh
    # queue) and the exit-code flip below all key on these lines, so removing
    # them makes every bare-host job read as "left the queue" the instant it
    # starts.
    echo "# PID wrapper: TBD             "
    echo "# PID uv: TBD             "
    echo "# PID python: TBD             "
    echo "# Exit code: running"
    echo "# --- dirty diff (tracked files; empty when clean; capped 64KB) ---"
    git -C "$REPO_ROOT" diff HEAD 2>/dev/null | head -c 65536
    echo "# ---"
} > "$LOG"

nohup env "${ENVS[@]}" bash -c '
    $1 "$2" "${@:4}" >> "$3" 2>&1
    ec=$?
    # portable in-place flip (BSD sed has no bare -i); cat-over keeps the inode
    tmp="$3.ecflip.$$"
    sed "s/^# Exit code: running/# Exit code: $ec/" "$3" > "$tmp" \
        && cat "$tmp" > "$3"
    rm -f "$tmp"
' _ "$RUNNER" "$PY_ABS" "$LOG" "$@" </dev/null >/dev/null 2>&1 &
WRAP_PID=$!

# payload PIDs — best-effort header debug info only (canonical id is
# WRAP_PID; "unknown" is fine, e.g. under a custom RUNNER)
sleep 3
# The wrapper's child is the runner itself. Under uv, python is uv's child;
# under any other runner the child is python (or a thin wrapper around it),
# and it is recorded as the python PID so liveness checks still have one.
RUN_PID=$(pgrep -P "$WRAP_PID" | head -1)
case "$RUNNER" in
    uv\ *) UV_PID=$RUN_PID; PY_PID=$(pgrep -P "${UV_PID:-0}" -f python | head -1) ;;
    *)     UV_PID=""; PY_PID=$RUN_PID ;;
esac

patch_line() {  # same-length in-place overwrite — keeps the inode (see header comment)
    local off len
    off=$(grep -ab "^$2" "$1" | head -1 | cut -d: -f1)
    [ -n "$off" ] || return 0
    len=$(grep -a "^$2" "$1" | head -1 | wc -c)
    printf '%-*s' $((len - 1)) "$2$3" | dd of="$1" bs=1 seek="$off" conv=notrunc status=none
}
patch_line "$LOG" "# PID wrapper: " "$WRAP_PID"
patch_line "$LOG" "# PID uv: " "${UV_PID:-unknown}"
patch_line "$LOG" "# PID python: " "${PY_PID:-unknown}"

kill -0 "$WRAP_PID" 2>/dev/null || echo "WARNING: job exited within 3s — check $LOG" >&2

# Post-submit record, done HERE so it cannot be skipped: launching and recording are
# one action. A polling safety net can never catch a job that starts and finishes
# between two snapshots (bare-host cells run in seconds), so the record must happen at
# submit time, not by later inspection.
RECORD_RC=0
if [ "$ENTRY" != none ]; then
    # PAGE/ENTRY_NAME/REC resolved by the pre-flight above.
    if [ -n "$REC" ]; then
        python3 "$REC" "$PAGE" "$ENTRY_NAME" "$WRAP_PID" "$LOG" ${BIND[@]+"${BIND[@]}"} >&2 || RECORD_RC=$?
    else
        echo "record_submit.py not found beside this launcher or in the installed plugin" >&2
        RECORD_RC=4
    fi
fi

echo "log: $LOG"
echo "$WRAP_PID"

# The job IS running either way (the PID above is real), but a launch whose record
# failed must never read as plain success: nothing polls for it later, so an
# unrecorded job is invisible forever. Exit non-zero so the caller has to act.
if [ "$RECORD_RC" -ne 0 ]; then
    echo "ERROR: job LAUNCHED but NOT RECORDED (record_submit exited $RECORD_RC) —" >&2
    echo "       reason is printed above. Record it BY HAND now: add" >&2
    echo "       $WRAP_PID to the owning entry's '- **Jobs:**' field," >&2
    echo "       link $LOG in that entry, and set it Status: running. ENTRY=$ENTRY" >&2
    echo "       Do NOT re-run this launcher: job $WRAP_PID is ALREADY running." >&2
    exit 3
fi
