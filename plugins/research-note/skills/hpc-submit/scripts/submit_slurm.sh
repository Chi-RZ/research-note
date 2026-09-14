#!/usr/bin/env bash
# Slurm submit + record as ONE action — the Case A/C mirror of
# launch_bare_gpu.sh. Submitting and recording are a single step for the same
# reason as on a bare host: nothing polls for a job that was never written to
# its entry, so an unrecorded job is invisible forever.
#
# Usage:
#   ENTRY="<node>/<page>: <entry name>" [TAG=<key_params>] [REMOTE=<host>] \
#       submit_slurm.sh <submit.slurm> [extra sbatch args...]
#
# Two environments, chosen automatically:
#   Case A — sbatch exists locally: you are ON the cluster, submit here.
#   Case C — no local sbatch but REMOTE_HOST/REMOTE_DIR are set in
#            .claude/hpc.env: ssh to the cluster and submit in the clone.
#            The page is LOCAL, so the record is written here, pointing at the
#            repo-relative log path the fixer will rsync back.
#            REMOTE=<host> picks WHICH declared cluster (multi-remote hpc.env:
#            REMOTE_HOSTS + REMOTE_DIR_<host>); unset = the default REMOTE_HOST.
#            A non-default host is recorded as `<jobid>@<host>` on the entry.
#
# Output: sbatch's own line, the resolved log path, and the job id LAST
# (liveness handle, same contract as launch_bare_gpu.sh).
#
# Exit 3 = submitted but NOT recorded — fix the page by hand in the SAME turn.
# NEVER re-run the launcher on exit 3: the job is ALREADY in the queue, and a
# retry submits a second one. The pre-flight below makes this path rare — a
# page or entry that will not resolve aborts BEFORE sbatch.

set -uo pipefail

[ "$#" -ge 1 ] || { echo "Usage: ENTRY=... [TAG=...] $0 <submit.slurm> [sbatch args...]" >&2; exit 1; }
: "${ENTRY:?ENTRY is required — \"<node>/<page>: <entry name>\". Every batch launch is a recorded run; a throwaway is a <30 min foreground uv run, not an sbatch.}"

SLURM_SCRIPT=$1; shift
[ -f "$SLURM_SCRIPT" ] || { echo "no such submit script: $SLURM_SCRIPT" >&2; exit 1; }

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not inside a git repo" >&2; exit 1; }
# Same rule as launch_bare_gpu: recorded evidence never lives in a worktree.
if [ "$ENTRY" != none ] && [ "$(git rev-parse --path-format=absolute --git-dir)" \
        != "$(git rev-parse --path-format=absolute --git-common-dir)" ]; then
    echo "submit_slurm: formal runs launch from main — this is a linked WORKTREE, and its logs die with it. ENTRY=none for a smoke, or launch from the main checkout." >&2; exit 1
fi
[ -f "$REPO_ROOT/.claude/hpc.env" ] && . "$REPO_ROOT/.claude/hpc.env"
[ -f "$REPO_ROOT/.claude/hpc.local.env" ] && . "$REPO_ROOT/.claude/hpc.local.env"

# Multi-remote: REMOTE=<ssh alias> retargets Case C to that cluster; its clone
# path is REMOTE_DIR_<alias> (non-alphanumerics in the alias map to `_`), with
# plain REMOTE_DIR the fallback for the default host only. Case A ignores it.
DEFAULT_RHOST=${REMOTE_HOST:-}
if [ -n "${REMOTE:-}" ]; then
    _V=REMOTE_DIR_$(printf '%s' "$REMOTE" | tr -c 'A-Za-z0-9_' '_')
    eval "_D=\${$_V:-}"
    [ -z "$_D" ] && [ "$REMOTE" = "$DEFAULT_RHOST" ] && _D=${REMOTE_DIR:-}
    [ -n "$_D" ] || { echo "REMOTE=$REMOTE but no $_V in .claude/hpc.env (and '$REMOTE' is not the default REMOTE_HOST)" >&2; exit 1; }
    REMOTE_HOST=$REMOTE
    REMOTE_DIR=$_D
fi

# Repo-relative paths: the cluster clone mirrors the repo, so ONE relative path
# is valid on both sides and the recorded link resolves locally after rsync.
ABS_SLURM=$(cd "$(dirname "$SLURM_SCRIPT")" && pwd)/$(basename "$SLURM_SCRIPT")
REL_SLURM=${ABS_SLURM#"$REPO_ROOT"/}
REL_EXP=$(dirname "$(dirname "$REL_SLURM")")     # experiments/<node>/<group>/submit/x.slurm -> experiments/<node>/<group>
REL_LOGDIR="$REL_EXP/logs"

STEM=$(basename "$SLURM_SCRIPT" .slurm)
NAME="$STEM${TAG:+-$TAG}"
REL_PATTERN="$REL_LOGDIR/slurm-$NAME-%j.out"

# Cluster facts live in hpc.env, not in each submit file (see the templates).
QUEUE=()
[ -n "${REMOTE_PARTITION:-}" ]   && QUEUE+=(--partition="$REMOTE_PARTITION")
[ -n "${REMOTE_RESERVATION:-}" ] && QUEUE+=(--reservation="$REMOTE_RESERVATION")
[ -n "${REMOTE_ACCOUNT:-}" ]     && QUEUE+=(--account="$REMOTE_ACCOUNT")
# `${QUEUE[@]+...}`: an EMPTY array under `set -u` is "unbound" on bash 3.2
# (stock macOS) and 4.2 (RHEL7) — a project declaring no queue placement died
# here with a shell error before sbatch, instead of submitting to the default.

# Pre-flight the record BEFORE anything reaches a queue: resolve the page and
# the entry now, so a typo'd ENTRY aborts with nothing submitted — found after
# the fact it costs a live job whose record failed, behind an exit 3 no retry
# may follow.
SD=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REC=""
for cand in "$SD/../../../scripts" "$SD/../scripts" "$SD"; do
    [ -f "$cand/record_submit.py" ] && { REC="$cand/record_submit.py"; break; }
done
[ -n "$REC" ] || REC=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | sort -V | tail -1)
[ -n "$REC" ] || REC=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | sort -V | tail -1)
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
            || { echo "pre-flight failed — fix ENTRY (\"$ENTRY\") or create the entry first; NOTHING was submitted" >&2; exit 1; }
    fi
fi

if command -v sbatch >/dev/null 2>&1; then
    WHERE="local cluster"
    mkdir -p "$REPO_ROOT/$REL_LOGDIR"
    OUT=$(cd "$REPO_ROOT" && sbatch ${QUEUE[@]+"${QUEUE[@]}"} -J "$NAME" -o "$REL_PATTERN" -e "$REL_PATTERN" "$@" "$REL_SLURM" 2>&1)
    RC=$?
else
    [ -n "${REMOTE_HOST:-}" ] && [ -n "${REMOTE_DIR:-}" ] || {
        echo "no local sbatch and no REMOTE_HOST/REMOTE_DIR in .claude/hpc.env" >&2; exit 1; }
    WHERE="$REMOTE_HOST:$REMOTE_DIR"
    # remote.sh push BEFORE anything reaches the queue: project ff-pulled and
    # SHA-checked, and every declared lib (LIB_<name>_*) held to clean +
    # pushed + SHA-equal.
    # Without this gate the cluster silently runs whatever lib version it last
    # pulled — the exact divergence the bridge exists to kill.
    RSH=""
    for cand in "$SD/../../../scripts" "$SD/../scripts" "$SD"; do
        [ -f "$cand/remote.sh" ] && { RSH="$cand/remote.sh"; break; }
    done
    [ -n "$RSH" ] || RSH=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/*/scripts/remote.sh 2>/dev/null | sort -V | tail -1)
    [ -n "$RSH" ] || RSH=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/*/scripts/remote.sh 2>/dev/null | sort -V | tail -1)
    [ -n "$RSH" ] || { echo "remote.sh not found beside this script or in the installed plugin" >&2; exit 1; }
    bash "$RSH" push --host "$REMOTE_HOST" || { echo "remote.sh push failed — nothing submitted" >&2; exit 1; }
    # A .slurm file needs a scheduler on the other side. remote.sh submit
    # dispatches (sbatch there / ship the bare launcher if not), but this path
    # hands over a submit FILE, which a bare host cannot consume — so refuse
    # with the working command instead of failing inside ssh with `sbatch: not
    # found` after the push already ran.
    if ! ssh -n -o BatchMode=yes "$REMOTE_HOST" 'command -v sbatch >/dev/null 2>&1'; then
        echo "submit_slurm: $REMOTE_HOST has no sbatch — a .slurm file cannot run there." >&2
        echo "  Use the bare-remote path instead:" >&2
        echo "    bash \"$RSH\" submit <script.py> <gpu_id|cpu> <mem_frac> [args...]" >&2
        exit 1
    fi
    # ssh -n everywhere a result is captured: an inherited stdin inside a
    # caller's `while read` loop swallows the worklist and the loop "succeeds"
    # after one iteration.
    OUT=$(ssh -n -o BatchMode=yes "$REMOTE_HOST" \
        "cd '$REMOTE_DIR' && mkdir -p '$REL_LOGDIR' && sbatch ${QUEUE[*]+${QUEUE[*]}} -J '$NAME' -o '$REL_PATTERN' -e '$REL_PATTERN' $* '$REL_SLURM'" 2>&1)
    RC=$?
fi

echo "$OUT"
[ "$RC" -eq 0 ] || { echo "sbatch failed on $WHERE" >&2; exit 1; }

JOB_ID=$(printf '%s' "$OUT" | grep -oE 'Submitted batch job [0-9]+' | grep -oE '[0-9]+$')
[ -n "$JOB_ID" ] || { echo "submitted to $WHERE but could not parse a job id from the output above" >&2; exit 1; }

# What the entry's `- **Jobs:**` field gets: a plain id means the default host;
# a NON-default cluster is tagged `<jobid>@<host>` so the record says where the
# job lives (the linter accepts both, matching stays host-agnostic).
REC_ID=$JOB_ID
[ "$WHERE" != "local cluster" ] && [ -n "$DEFAULT_RHOST" ] \
    && [ "$REMOTE_HOST" != "$DEFAULT_RHOST" ] && REC_ID="$JOB_ID@$REMOTE_HOST"

REL_LOG=${REL_PATTERN/\%j/$JOB_ID}

# Job-start check: PENDING is a perfectly good answer on a busy queue — this
# only catches a submission the scheduler already threw away.
if command -v sbatch >/dev/null 2>&1; then
    STATE=$(squeue -j "$JOB_ID" -h -o "%T" 2>/dev/null | head -1)
    [ -n "$STATE" ] || STATE=$(sacct -j "$JOB_ID" -n -o State%-20 2>/dev/null | head -1 | awk '{print $1}')
else
    STATE=$(ssh -n -o BatchMode=yes "$REMOTE_HOST" \
        "squeue -j $JOB_ID -h -o '%T' 2>/dev/null | head -1" 2>/dev/null)
fi
echo "state: ${STATE:-unknown} on $WHERE"
case "${STATE:-}" in
    FAILED|CANCELLED|TIMEOUT|NODE_FAIL|OUT_OF_MEMORY)
        echo "job $JOB_ID is already $STATE — not recording a dead job" >&2; exit 1 ;;
esac

RECORD_RC=0
if [ "$ENTRY" != none ]; then
    # PAGE/ENTRY_NAME/REC resolved by the pre-flight above.
    if [ -n "$REC" ]; then
        python3 "$REC" "$PAGE" "$ENTRY_NAME" "$REC_ID" "$REPO_ROOT/$REL_LOG" ${BIND[@]+"${BIND[@]}"} >&2 || RECORD_RC=$?
    else
        echo "record_submit.py not found beside this script or in the installed plugin" >&2
        RECORD_RC=4
    fi
fi

echo "log: $REL_LOG"
echo "$JOB_ID"

if [ "$RECORD_RC" -ne 0 ]; then
    echo "ERROR: job SUBMITTED but NOT RECORDED (record_submit exited $RECORD_RC) —" >&2
    echo "       record it BY HAND now: add $REC_ID to the owning entry's" >&2
    echo "       '- **Jobs:**' field, link $REL_LOG in that entry, set it" >&2
    echo "       Status: running. ENTRY=$ENTRY" >&2
    echo "       Do NOT re-run this launcher: job $JOB_ID is ALREADY in the queue." >&2
    exit 3
fi
