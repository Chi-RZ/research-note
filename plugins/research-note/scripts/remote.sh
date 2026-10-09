#!/usr/bin/env bash
# remote.sh — the general remote-HPC bridge (rules layer; no Claude runs on the
# cluster). Everything cluster-specific is PROJECT configuration:
#
#   <project>/.claude/hpc.env          (tracked — project profile)
#     REMOTE_HOST=hpc                  # DEFAULT host: ssh alias (~/.ssh/config; BatchMode must work)
#     REMOTE_DIR=/path/on/cluster      # default host's git clone of THIS repo
#     REMOTE_DATA_MAX_MB=50            # per-file cap for `pull`ing data/ (0 = logs only)
#     REMOTE_HOSTS="hpc other"         # optional: ALL clusters, space-separated — no
#                                      # primary/secondary, every listed host is
#                                      # monitored equally; unset = just REMOTE_HOST
#     REMOTE_DIR_hpc=/path/on/hpc      # per-host clone paths (non-alphanumerics in
#     REMOTE_DIR_other=/path/on/other  # the alias map to `_`; plain REMOTE_DIR is
#                                      # the fallback for the default host only)
#   <project>/.research-note/editables.env
#                                      (optional — real path per machine for
#                                       libraries developed editable)
#
# Subcommands (all idempotent, all run FROM the local machine). `queue`, `pull`
# and `push` loop over ALL declared hosts; `--host <h>` right after the
# subcommand pins any subcommand to one host (setup/submit take the default
# host otherwise):
#   setup   clone the host's dir from this repo's Git origin if missing, else
#           ff-pull; print both SHAs. A FRESH clone is sparse (cone: src/ tests/
#           experiments/ + root files — the cluster runs jobs, it never needs
#           project_memory/ or a knowledge root; .claude/ travels, the submit templates read hpc.env from it), with an old-git pattern fallback.
#   push    local `git push` -> each host's `merge --ff-only` -> hard SHA equality check
#   queue   `squeue -u $USER` snapshot from EVERY host, kept to the jobs whose
#           WorkDir is under that host's $REMOTE_DIR -> <project>/.fixer/remote_queue
#           (one 'jobid STATE @host' per line; consumed by the linter's J3/J4 and
#           the board — the leading jobid keeps single-host consumers unchanged)
#   pull    rsync back experiments/**/logs/** (all) + experiments/**/data/** (files
#           <= REMOTE_DATA_MAX_MB) from EVERY host; the big artifacts stay there
#   submit  push, then run the job in REMOTE_DIR over ssh; LAST line = job id (the
#           hpc-submit record contract). Dispatches on the REMOTE, like `queue`:
#             sbatch there  -> `sbatch <args>`, job id = Slurm's
#             no sbatch     -> ships the Case B launcher into .fixer/ and runs it
#                              with ENTRY=none; args are the launcher's
#                              (<script.py> <gpu_id|cpu> <mem_frac> [args...]),
#                              job id = the wrapper PID, which is what `queue` sees
#   status  config + snapshot age at a glance
#
# ssh note: remote outputs are captured via TEMP FILES with stdin </dev/null, never
# `var=$(ssh ...)` — under ControlMaster the master holds a copy of the substitution
# pipe fd and a later pipeline deadlocks on it.
set -uo pipefail

CMD=${1:-status}; shift || true

PROJ="${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}"
while [ "$PROJ" != "/" ] && [ ! -f "$PROJ/.claude/framework.json" ] \
      && [ ! -f "$PROJ/.claude/roles.json" ] \
      && [ ! -f "$PROJ/.research-note/project.json" ]; do PROJ=$(dirname "$PROJ"); done
if [ ! -f "$PROJ/.claude/framework.json" ] && [ ! -f "$PROJ/.claude/roles.json" ] \
        && [ ! -f "$PROJ/.research-note/project.json" ]; then
    echo "remote.sh: not inside a framework project (and project-dir overrides unset)" >&2
    exit 2
fi

[ -f "$PROJ/.claude/hpc.env" ] && . "$PROJ/.claude/hpc.env"
[ -f "$PROJ/.claude/hpc.local.env" ] && . "$PROJ/.claude/hpc.local.env"
[ -f "$PROJ/.research-note/editables.env" ] && . "$PROJ/.research-note/editables.env"
. "$(dirname "${BASH_SOURCE[0]}")/lib_paths.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KNOWLEDGE_ROOTS=wiki
EXPERIMENT_ROOTS=experiments
ENV_MANAGER=uv
if [ -f "$PROJ/.research-note/project.json" ]; then
    KNOWLEDGE_ROOTS=$(python3 "$HERE/project_config.py" --project "$PROJ" role knowledge) || exit 2
    EXPERIMENT_ROOTS=$(python3 "$HERE/project_config.py" --project "$PROJ" role experiments) || exit 2
    # ONE LINE each. `role` prints one root per line, and these are interpolated
    # into commands built as TEXT for the far side: a newline inside a `for`
    # list splits it across two lines and the remote shell sees a syntax error,
    # so a project with two experiment roots got an empty queue snapshot — which
    # reads as "every job left the queue", not as "cannot tell". Unquoted on
    # purpose: word-splitting is what joins them.
    KNOWLEDGE_ROOTS=$(printf '%s ' $KNOWLEDGE_ROOTS)
    EXPERIMENT_ROOTS=$(printf '%s ' $EXPERIMENT_ROOTS)
    ENV_MANAGER=$(python3 "$HERE/project_config.py" --project "$PROJ" environment 2>/dev/null || echo uv)
fi
SPARSE_PATTERNS="'/*' '!/project_memory/'"
SPARSE_EXCLUDES="'/project_memory/'"
for root in $KNOWLEDGE_ROOTS; do
    SPARSE_PATTERNS="$SPARSE_PATTERNS '!/$root/'"
    SPARSE_EXCLUDES="$SPARSE_EXCLUDES '/$root/'"
done
if [ -z "${REMOTE_HOST:-}" ] || [ -z "${REMOTE_DIR:-}" ]; then
    echo "remote.sh: REMOTE_HOST / REMOTE_DIR not declared in $PROJ/.claude/hpc.env" >&2
    exit 2
fi
# LogLevel=ERROR, not WarnWeakCrypto=no-pq-kex: OpenSSH 10 prints a three-line
# post-quantum banner on every connection to an older server, and it lands in
# whatever captures stderr — the fixer's log entry was nothing else for weeks.
# The dedicated switch exists but only in 10.1+, and an older client aborts on an
# unknown option; ERROR has been understood by every version and still lets a
# refused connection, a bad key and a resolution failure through.
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR)
STATE="$PROJ/.fixer"; mkdir -p "$STATE"
BR=$(git -C "$PROJ" branch --show-current)

# Multi-remote: HOSTS is the full host list (REMOTE_HOSTS, or the single-host
# back-compat list "$REMOTE_HOST"); the default host is always a member. The
# looping subcommands reassign REMOTE_HOST/REMOTE_DIR per host, so the default
# pair is pinned here for host_dir's fallback.
DEFAULT_HOST=$REMOTE_HOST; DEFAULT_DIR=$REMOTE_DIR
HOSTS=${REMOTE_HOSTS:-$REMOTE_HOST}
case " $HOSTS " in *" $REMOTE_HOST "*) ;; *) HOSTS="$REMOTE_HOST $HOSTS" ;; esac
host_dir() {   # host_dir <host> -> that host's project clone path
    local v d
    v=REMOTE_DIR_$(printf '%s' "$1" | tr -c 'A-Za-z0-9_' '_')
    eval "d=\${$v:-}"
    [ -z "$d" ] && [ "$1" = "$DEFAULT_HOST" ] && d=$DEFAULT_DIR
    [ -n "$d" ] || { echo "remote.sh: no $v in .claude/hpc.env (and '$1' is not the default host)" >&2; return 1; }
    printf '%s\n' "$d"
}
# `--host <h>` right after the subcommand pins this invocation to one host;
# single-host operations (setup, submit) otherwise act on the default host,
# looping ones (queue, pull, push) otherwise cover every declared host.
LOOP_HOSTS=$HOSTS
if [ "${1:-}" = "--host" ]; then
    [ -n "${2:-}" ] || { echo "remote.sh: --host wants a host alias" >&2; exit 2; }
    REMOTE_DIR=$(host_dir "$2") || exit 2
    REMOTE_HOST=$2
    LOOP_HOSTS=$2
    shift 2
fi

rssh() {   # rssh <cmd...>  -> runs on the cluster, stdout to our stdout
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "$@" </dev/null
}

case "$CMD" in
setup)
    URL=$(git -C "$PROJ" remote get-url origin) || { echo "remote.sh: local repo has no origin — the cluster syncs from that Git remote" >&2; exit 1; }
    if ! rssh "test -d '$REMOTE_DIR/.git'"; then
        echo "remote.sh: sparse-cloning $URL -> $REMOTE_HOST:$REMOTE_DIR (without project_memory/ and $KNOWLEDGE_ROOTS)"
        # SPARSE by default, expressed as an EXCLUDE list rather than a cone.
        # What the cluster must not carry is the record: project_memory/ and
        # wiki/ have no effect on a job and every effect on a reader, who finds a
        # stale page there and believes it. What it must carry is whatever this
        # project runs from — and only the project knows what that is. A cone
        # names the keepers, so `--cone src tests experiments .claude` silently
        # deletes a project whose source lives in code/ or lib/; the exclude list
        # cannot, because it names the two directories that are never needed.
        # It is also the portable form: `git sparse-checkout` arrived in 2.25 and
        # cluster git is routinely 1.8, where core.sparseCheckout + the pattern
        # file is the only spelling. One form, every git.
        # .git/info/exclude then hides anything created outside the checkout
        # (hpc.local.env, monitor output, ...) so `status` stays clean and push's
        # ff-merge is undisturbed.
        rssh "git clone -q --no-checkout '$URL' '$REMOTE_DIR' && cd '$REMOTE_DIR' && \
              git config core.sparseCheckout true && \
              printf '%s\n' $SPARSE_PATTERNS > .git/info/sparse-checkout && \
              printf '%s\n' $SPARSE_EXCLUDES >> .git/info/exclude && \
              git checkout -q '$BR'" || exit 1
    fi
    # MIGRATION: a clone made before sparse was the default (or by hand) still
    # carries project_memory/ or a knowledge root. Rewriting the pattern file is idempotent
    # and never removes anything else, so setup repairs it on every run.
    rssh "cd '$REMOTE_DIR' && git config core.sparseCheckout true && \
          printf '%s\n' $SPARSE_PATTERNS > .git/info/sparse-checkout && \
          git read-tree -mu HEAD" || true
    rssh "cd '$REMOTE_DIR' && git fetch -q origin && git checkout -q '$BR' && git merge -q --ff-only 'origin/$BR'" || {
        echo "remote.sh: remote checkout/ff failed — remote working copy diverged? Fix by hand (it must stay a pure mirror)" >&2; exit 1; }
    # Give uv stable project-local paths before it resolves the environment.
    bash "$HERE/sync_editables.sh" --host "$REMOTE_HOST" --remote-dir "$REMOTE_DIR" || exit 1
    # Align the remote environment HERE, on the login node, where installing is
    # allowed and visible — never inside a job (batch runs use `--no-sync`).
    # `uv sync` or a uv version change can re-text uv.lock without changing the
    # resolution. Discard that rewrite: a dirty mirror stamps every log header
    # `(dirty)` and blocks the next ff. A no-op when nothing changed.
    # uv only: under another manager the project installs its own environment
    # and nothing here can bring the far side up to a lock it does not have
    [ "$ENV_MANAGER" = uv ] && { rssh "cd '$REMOTE_DIR' && uv sync -q >/dev/null 2>&1; git checkout -- uv.lock 2>/dev/null" || true; }
    T=$(mktemp); rssh "cd '$REMOTE_DIR' && git rev-parse --short HEAD" >"$T"
    echo "local  @ $(git -C "$PROJ" rev-parse --short HEAD) ($BR)"
    echo "remote @ $(cat "$T") ($REMOTE_HOST:$REMOTE_DIR)"; rm -f "$T"
    ;;
push)
    if [ -n "$(git -C "$PROJ" status --porcelain)" ]; then
        echo "remote.sh push: local worktree dirty — commit first (the record rules want that anyway)" >&2; exit 1
    fi
    git -C "$PROJ" push -q origin "$BR" || exit 1
    L=$(git -C "$PROJ" rev-parse HEAD)
    # EVERY declared host (or the one pinned by --host) is held to the same
    # mirror discipline; any host failing fails the push.
    for RH in $LOOP_HOSTS; do
    REMOTE_DIR=$(host_dir "$RH") || exit 1
    REMOTE_HOST=$RH
    # Artifacts the cluster produced (logs, cells) come home via `pull` and are
    # committed HERE; the cluster's own untracked copies then block the very next
    # ff-merge with "untracked working tree files would be overwritten". Every
    # submit after the first would fail. They are the same bytes — the commit came
    # FROM them — so drop the ones whose content matches the incoming blob and let
    # git restore them. One that does NOT match is real divergence: leave it, and
    # the merge below stops the push, which is what should happen.
    rssh "cd '$REMOTE_DIR' && git fetch -q origin && \
          git diff --name-only --diff-filter=A HEAD 'origin/$BR' | while IFS= read -r f; do
              [ -e \"\$f\" ] || continue
              [ \"\$(git hash-object \"\$f\")\" = \"\$(git rev-parse \"origin/$BR:\$f\" 2>/dev/null)\" ] && rm -f \"\$f\"
          done; true" || exit 1
    rssh "cd '$REMOTE_DIR' && git merge -q --ff-only 'origin/$BR'" || exit 1
    # One path contract and one action own editable libraries. Real paths may
    # differ; both project-local slots resolve before uv inspects them.
    bash "$HERE/sync_editables.sh" --host "$RH" --remote-dir "$REMOTE_DIR" || exit 1
    # Align the remote environment on the login node after those slots exist.
    rssh "cd '$REMOTE_DIR' && VIRTUAL_ENV= uv sync -q >/dev/null 2>&1; git checkout -- uv.lock 2>/dev/null" || true
    # Julia gets the same treatment, in the same place, for the same reason: the
    # spec file is what crossed, so bring the far side up to it BEFORE checking
    # it, rather than reporting a difference the machine could have closed
    # itself. JULIA_PROJECT (hpc.env, repo-relative) is how a project says it has
    # one; unset means it does not, and nothing here runs.
    if [ -n "${JULIA_PROJECT:-}" ]; then
        rssh "bash -lc 'command -v julia >/dev/null || exit 0; cd \"$REMOTE_DIR/$JULIA_PROJECT\" && julia --project=. -e \"using Pkg; Pkg.instantiate()\"'" >/dev/null 2>&1 || true
    fi
    T=$(mktemp); rssh "cd '$REMOTE_DIR' && git rev-parse HEAD" >"$T"; R=$(cat "$T"); rm -f "$T"
    if [ "$L" != "$R" ]; then
        echo "remote.sh push: SHA mismatch — local $L vs $REMOTE_HOST $R" >&2; exit 1
    fi
    # Pin drift. The fingerprint below cannot see it: a git-pinned fork with a
    # static version (`quantax==0.3.0`) fingerprints identically across revs, so
    # a project could push code that runs a months-old fork with nothing saying
    # so. bump_lib --check compares each pin against its local checkout.
    BL="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/bump_lib.sh"
    if [ -z "${SKIP_PIN_CHECK:-}" ] && [ -f "$BL" ] && grep -q 'git = ' "$PROJ/pyproject.toml" 2>/dev/null; then
        if ! (cd "$PROJ" && bash "$BL" --check >/dev/null 2>&1); then
            echo "remote.sh push: PIN DRIFT — a fork's checkout has moved past the rev this project pins:" >&2
            (cd "$PROJ" && bash "$BL" --check 2>&1 | sed 's/^/  /') >&2
            echo "  Fix: bump_lib.sh --all, commit pyproject.toml + uv.lock, retry." >&2
            echo "  (Intentional? SKIP_PIN_CHECK=1 — the run then uses the pinned rev, not your checkout.)" >&2
            exit 1
        fi
        echo "pins current"
    fi

    # Environment parity. The lib gate above compares the SOURCE both sides run;
    # this compares what is INSTALLED around it — a package present that the lock
    # does not name (an optional accelerator, say: kahypar changes the contraction
    # path quimb picks) makes the same code take a different route, and no SHA
    # sees it. Checked HERE because push is the moment code crosses over and the
    # login node is where an install is allowed. SKIP_ENV_CHECK=1 to proceed.
    #
    # The venv is measured against the LOCKFILE, on the machine that will run the
    # job — not against this laptop. One lock resolves to a DIFFERENT installed
    # set per platform (a Mac gets no nvidia-* wheels; the markers are in the lock
    # and say so), so comparing the two machines was permanently red on any
    # Mac/Linux pair while both sides were in fact exactly right — and a gate that
    # is always red is a gate everyone learns to skip. `uv sync --check` is
    # read-only, knows the markers because it runs where they apply, and catches
    # two things the comparison never could: a package installed on the cluster
    # that the lock does not name, and a lock stale against pyproject.
    # `bash -lc`: uv routinely lives in ~/.local/bin, which a non-interactive ssh
    # does not have on PATH. rc 3 = no uv there, which is a different answer from
    # "the venv is wrong" and must not be reported as one.
    if [ "$ENV_MANAGER" != uv ]; then
        echo "env parity: not checked (environment.manager = $ENV_MANAGER — no lock file to compare)"
    elif [ -z "${SKIP_ENV_CHECK:-}" ]; then
        ENVOUT=$(rssh "bash -lc 'command -v uv >/dev/null || exit 3; cd \"$REMOTE_DIR\" && uv sync --check'" 2>&1) || ENVRC=$?
        case "${ENVRC:-0}" in
            0) echo "env parity ok (remote venv matches uv.lock)" ;;
            3) echo "remote.sh push: no uv on $REMOTE_HOST — its venv cannot be checked against uv.lock" >&2
               echo "  Fix: install uv there, or SKIP_ENV_CHECK=1 to proceed unchecked." >&2
               exit 1 ;;
            *) echo "remote.sh push: $REMOTE_HOST's venv does not match uv.lock" >&2
               printf '%s\n' "$ENVOUT" | tail -5 | sed 's/^/  /' >&2
               echo "  Fix: ssh $REMOTE_HOST 'cd $REMOTE_DIR && uv sync' (login node is fine — it is not compute)." >&2
               echo "  SKIP_ENV_CHECK=1 overrides." >&2
               exit 1 ;;
        esac
        unset ENVRC
        # Julia, same shape: the environment is right when every package the
        # Manifest names has its source on disk. Asked AFTER the instantiate
        # above, so a difference here is one the machine could not close itself.
        if [ -n "${JULIA_PROJECT:-}" ]; then
            JOUT=$(rssh "bash -lc 'command -v julia >/dev/null || exit 3; cd \"$REMOTE_DIR/$JULIA_PROJECT\" && julia --project=. -e \"using Pkg; d=Pkg.dependencies(); m=[p.name for (u,p) in d if p.source===nothing || !isdir(p.source)]; isempty(m) ? println(\\\"ok \\\", length(d), \\\" packages\\\") : (println(\\\"missing: \\\", join(m, \\\",\\\")); exit(1))\"'" 2>&1) || JRC=$?
            case "${JRC:-0}" in
                0) echo "julia parity ok ($JULIA_PROJECT: $(printf '%s' "$JOUT" | tail -1))" ;;
                3) echo "remote.sh push: no julia on $REMOTE_HOST — $JULIA_PROJECT cannot be checked against its Manifest" >&2
                   echo "  Fix: install julia there, or SKIP_ENV_CHECK=1 to proceed unchecked." >&2
                   exit 1 ;;
                *) echo "remote.sh push: $REMOTE_HOST's $JULIA_PROJECT does not match its Manifest" >&2
                   printf '%s\n' "$JOUT" | tail -3 | sed 's/^/  /' >&2
                   echo "  Fix: ssh $REMOTE_HOST 'cd $REMOTE_DIR/$JULIA_PROJECT && julia --project=. -e \"using Pkg; Pkg.instantiate()\"'." >&2
                   echo "  SKIP_ENV_CHECK=1 overrides." >&2
                   exit 1 ;;
            esac
            unset JRC
        fi
        # Variants, checked HERE too and not only in doctor: doctor is read when
        # someone wonders, push runs when code crosses. It is a file comparison
        # in git, so it costs nothing and blocks a submit whose two environments
        # have silently stopped describing the same stack.
        if [ -n "${JULIA_PROJECT:-}" ] && [ -n "${JULIA_PROJECT_VARIANTS:-}" ]; then
            VM=""; for VAR in $JULIA_PROJECT_VARIANTS; do VM="$VM $PROJ/$VAR/Manifest.toml"; done
            if ! python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/julia_variants.py" \
                    "$PROJ/$JULIA_PROJECT/Manifest.toml" $VM; then
                echo "remote.sh push: a Julia variant no longer contains the base env" >&2
                echo "  SKIP_ENV_CHECK=1 overrides." >&2
                exit 1
            fi
        fi
    fi
    echo "synced $REMOTE_HOST @ ${L:0:7}"
    done
    ;;
queue)
    # One snapshot covering EVERY declared host, each row tagged `@<host>` so
    # downstream consumers can tell the hosts apart (the leading jobid keeps
    # single-host readers unchanged). ANY host failing keeps the previous
    # snapshot whole: a partial snapshot would read as "job left the queue"
    # (J3) for every job on the missing host, which is worse than going stale.
    # The temp file lives IN $STATE: mktemp's default lands on $TMPDIR, which
    # is routinely a different filesystem (tmpfs /tmp, macOS /var/folders),
    # and a cross-device mv is copy+unlink — NOT atomic. The harvest hook
    # reads this file every turn and Monitors poll it, so a torn read would
    # show a truncated queue and invent a J3 for every job on the missing
    # tail. Same filesystem -> rename(2) -> readers see old or new, never half.
    ALL=$(mktemp "$STATE/remote_queue.XXXXXX")
    for RH in $LOOP_HOSTS; do
        REMOTE_DIR=$(host_dir "$RH") || { rm -f "$ALL"; exit 1; }
        REMOTE_HOST=$RH
        T=$(mktemp)
        # Scoped to THIS project by the job's WorkDir, exactly as the bare-remote
        # branch below scopes by $REMOTE_DIR: `squeue -u $USER` is the whole
        # account, so an unscoped snapshot hands every project on the cluster —
        # including projects not on this framework — to every project's J4 as an
        # "unrecorded" job, permanently. Compared after `pwd -P` on both sides:
        # REMOTE_DIR is routinely a symlink into a group filesystem, so a plain
        # string prefix drops the project's OWN jobs. If the dir will not resolve
        # the filter is skipped entirely — going back to the old noise beats going
        # blind to a real job. `|| exit 1` keeps squeue's failure visible: a
        # while-loop pipeline would otherwise exit 0 and mask it.
        if rssh 'R=$(cd "'"$REMOTE_DIR"'" 2>/dev/null && pwd -P)
Q=$(squeue -u "$USER" -h -o "%A %T %Z") || exit 1
printf "%s\n" "$Q" | while read -r id st wd; do
  [ -n "$id" ] || continue
  if [ -z "$R" ]; then echo "$id $st"; continue; fi
  w=$(cd "$wd" 2>/dev/null && pwd -P)
  case "$w" in "$R"|"$R"/*) echo "$id $st";; esac
done' >"$T" 2>/dev/null; then
            :
        elif ! rssh 'command -v squeue >/dev/null'; then
            # Bare remote (no Slurm): the launcher's live wrapper PIDs ARE the queue —
            # the same rule as the linter's live_bare_job_ids, read from the
            # `launch_bare_gpu.sh` log headers the remote wrote, NOT by scanning the
            # cluster's /proc for job-shaped processes. Scanning conflated one launch
            # (wrapper + uv + python all carry the absolute script path in argv) with
            # three jobs while only the wrapper PID is ever recorded, and could not tell a
            # submitted job from a foreground debug run. `# PID wrapper:` is read
            # (falling back to `# PID uv:` for logs older than 0.10.2), so
            # the ids here are the ids the entries carry. Emits 'pid RUNNING' lines so
            # every consumer of the snapshot (J3/J4 lint, the board's Running tab)
            # reads it unchanged.
            if ! rssh 'RD=$(cd "'"$REMOTE_DIR"'" 2>/dev/null && pwd -P) || exit 0
hz=$(getconf CLK_TCK 2>/dev/null || echo 100)
btime=$(awk "/^btime /{print \$2}" /proc/stat 2>/dev/null)
for experiment_root in '"$EXPERIMENT_ROOTS"'; do
  [ -d "$RD/$experiment_root" ] || continue
  find "$RD/$experiment_root" -path "*/logs/*.log" -type f 2>/dev/null
done | while read -r f; do
  set -- $(awk "NR>30{exit}
    /^# Exit code:/{ec=\$4} /^# PID wrapper:/{wpid=\$4} /^# PID uv:/{upid=\$4} /^# Timestamp:/{ts=\$3}
    END{pid=(wpid?wpid:upid); printf \"%s %s %s\", (ec?ec:\"-\"), (pid?pid:\"-\"), (ts?ts:\"-\")}" "$f")
  [ "$1" = running ] || continue
  case "$2" in ""|*[!0-9]*) continue;; esac
  kill -0 "$2" 2>/dev/null || continue
  # PID-reuse guard (mirror of PID_REUSE_TOLERANCE_S): a header only reaches a
  # terminal exit code if the wrapper lived to flip it, so a hard kill or reboot
  # leaves it saying `running` and PID space wraps. Unresolvable clock -> trust
  # the header, never let a probe failure hide a live job.
  st=$(date -d "$3" +%s 2>/dev/null)
  ticks=$(sed "s/.*) //" "/proc/$2/stat" 2>/dev/null | cut -d" " -f20)
  if [ -n "$st" ] && [ -n "$btime" ] && [ -n "$ticks" ]; then
    began=$((btime + ticks / hz))
    d=$((began - st)); [ "$d" -lt 0 ] && d=$((-d))
    [ "$d" -le 300 ] || continue
  fi
  echo "$2 RUNNING"
done
true' >"$T" 2>/dev/null; then
                rm -f "$T" "$ALL"
                echo "remote.sh queue: snapshot FAILED on $RH (previous one kept, will read as stale)" >&2
                exit 1
            fi
        else
            rm -f "$T" "$ALL"
            echo "remote.sh queue: snapshot FAILED on $RH (previous one kept, will read as stale)" >&2
            exit 1
        fi
        sed "s/\$/ @$RH/" "$T" >>"$ALL"; rm -f "$T"
    done
    mv "$ALL" "$STATE/remote_queue"
    echo "remote queue: $(wc -l < "$STATE/remote_queue" | tr -d ' ') job(s) on:$(printf ' %s' $LOOP_HOSTS)"
    ;;
pull)
    # Overwrite safety, two halves (deletions never propagate — no --delete):
    #   -u        skip files the LOCAL side has newer (a local edit is never
    #             silently reverted by an older remote copy)
    #   --backup  any file that IS overwritten (a running job's log growing is
    #             the legitimate case) first has its previous version saved to
    #             .fixer/pull_overwrites/ — an overwrite is recoverable, never
    #             silent. Bounded: the dir holds one previous version per file.
    BAK="$STATE/pull_overwrites"
    MAX=${REMOTE_DATA_MAX_MB:-50}
    # EVERY declared host in turn; one host down must not block the others, so
    # failures are collected (exit 1 at the end) rather than aborting the loop.
    RC=0
    for RH in $LOOP_HOSTS; do
        REMOTE_DIR=$(host_dir "$RH") || { RC=1; continue; }
        REMOTE_HOST=$RH
        # -e: rsync spawns its own ssh, which would otherwise miss SSH_OPTS and
        # keep printing the banner into the fixer's log — the half of the noise
        # that survives fixing rssh.
        found_experiments=0
        for experiment_root in $EXPERIMENT_ROOTS; do
            # A fresh clone may have no ignored output tree yet. Missing output
            # is an empty result, not an rsync failure.
            if ! rssh "test -d '$REMOTE_DIR/$experiment_root'"; then
                continue
            fi
            found_experiments=1
            # logs: everything (they are small and are the record's evidence)
            rsync -azu -e "ssh ${SSH_OPTS[*]}" --prune-empty-dirs --backup --backup-dir="$BAK" \
                --include='*/' --include='*/*/logs/***' --exclude='*' \
                "$REMOTE_HOST:$REMOTE_DIR/$experiment_root/" "$PROJ/$experiment_root/" || { RC=1; continue; }
            # data: capped per file — the big artifacts stay on the cluster by design
            if [ "$MAX" != "0" ]; then
                rsync -azu -e "ssh ${SSH_OPTS[*]}" --prune-empty-dirs --max-size="${MAX}m" --backup --backup-dir="$BAK" \
                    --include='*/' --include='*/*/data/***' --exclude='*' \
                    "$REMOTE_HOST:$REMOTE_DIR/$experiment_root/" "$PROJ/$experiment_root/" || { RC=1; continue; }
            fi
        done
        if [ "$found_experiments" -eq 0 ]; then
            echo "remote.sh pull: $REMOTE_HOST:$REMOTE_DIR has no configured experiment output yet — nothing to pull"
            continue
        fi
        echo "pulled logs (+data <= ${MAX}MB) from $REMOTE_HOST"
    done
    # The freshness stamp only advances when EVERY host delivered — a stale
    # stamp on a half-failed pull is the honest signal.
    [ "$RC" -eq 0 ] && date +%s > "$STATE/remote_last_pull"
    exit "$RC"
    ;;
submit)
    if [ "$#" -lt 1 ]; then
        echo "Usage: remote.sh submit <sbatch args...>                             (Slurm remote)" >&2
        echo "       remote.sh submit <script.py> <gpu_id|cpu> <mem_frac> [args...] (bare remote)" >&2
        exit 2
    fi
    # Same precondition the local launchers enforce: naming the entry is not
    # optional, because a remote job runs where nothing can record it later.
    # ENTRY=none stays available, but it has to be said out loud.
    : "${ENTRY:?ENTRY is required — set ENTRY=\"<node>/<page>: <entry name>\". Every remote launch is a recorded run — the cluster is not a place to run something you did not mean to keep.}"
    # Recorded evidence never launches from a worktree (same rule as the local
    # launchers): the pulled-back log would be linked from a page that outlives
    # the checkout the paths were computed against.
    if [ "${ENTRY:-none}" != none ] && [ "$(git -C "$PROJ" rev-parse --path-format=absolute --git-dir)" \
            != "$(git -C "$PROJ" rev-parse --path-format=absolute --git-common-dir)" ]; then
        echo "remote.sh submit: formal runs launch from main — this is a linked WORKTREE, and its logs die with it. ENTRY=none for a smoke, or launch from the main checkout." >&2; exit 1
    fi
    # The phase this launch serves, forwarded to both record calls below. A
    # launch comes FROM a phase, so the binding is known here and nowhere
    # later; record_submit writes the Plan line and REFUSES without it.
    # Remote is the venue that needs saying twice: the job runs there and the
    # record lives HERE, so the remote launcher runs `ENTRY=none` and never
    # records — these two call sites are the only ones, and a launcher that
    # forgets them refuses every launch that named an entry.
    BIND=()
    [ -n "${PHASE:-}" ] && BIND+=(--phase "$PHASE")
    [ -n "${ROLE:-}" ]  && BIND+=(--role "$ROLE")
    [ "${NO_OBJECTIVE:-0}" = 1 ] && BIND+=(--no-objective)
    # Pre-flight the record BEFORE the push and the launch: resolve the page
    # and the entry now, so a typo'd ENTRY aborts with nothing running — found
    # after the fact it costs a live cluster job whose record failed, behind
    # an exit 3 no retry may follow.
    if [ "${ENTRY:-none}" != none ]; then
        RS="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/record_submit.py"
        [ -f "$RS" ] || RS=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
        [ -f "$RS" ] || RS=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
        if [ -f "$RS" ]; then
            RPAGE=${ENTRY%%:*}; RNAME=${ENTRY#*:}; RNAME=${RNAME# }
            python3 "$RS" --check "$RPAGE" "$RNAME" ${BIND[@]+"${BIND[@]}"} >&2 \
                || { echo "remote.sh submit: pre-flight failed — fix ENTRY (\"$ENTRY\") or create the entry first; NOTHING was launched" >&2; exit 1; }
        fi
    fi
    # Push only the TARGET host's clone — a peer cluster being down must not
    # block this submit; the peers ff-pull at their own submit time.
    "$0" push --host "$REMOTE_HOST" || exit 1
    Q=$(printf ' %q' "$@")
    # Queue placement, the same three keys `submit_slurm.sh` applies — hpc.env is
    # already sourced above, and this branch simply never read it. Both `.slurm`
    # templates tell the writer that "queue placement comes from .claude/hpc.env
    # ... applied by the submit step", so a submit file correctly carries no
    # partition; a submit step that then drops them queues every remote job in
    # whatever the cluster defaults to, which is the exact cost those comments
    # name. Placed BEFORE the caller's args so an explicit flag still wins.
    QUEUE=""
    [ -n "${REMOTE_PARTITION:-}" ]   && QUEUE="$QUEUE $(printf %q "--partition=$REMOTE_PARTITION")"
    [ -n "${REMOTE_RESERVATION:-}" ] && QUEUE="$QUEUE $(printf %q "--reservation=$REMOTE_RESERVATION")"
    [ -n "${REMOTE_ACCOUNT:-}" ]     && QUEUE="$QUEUE $(printf %q "--account=$REMOTE_ACCOUNT")"
    T=$(mktemp)
    if rssh 'command -v sbatch >/dev/null 2>&1'; then
        if ! rssh "cd '$REMOTE_DIR' && sbatch$QUEUE$Q" >"$T" 2>&1; then
            cat "$T" >&2; rm -f "$T"; exit 1
        fi
        cat "$T"
        JID=$(grep -o '[0-9]\+' "$T" | tail -1); rm -f "$T"
        [ -n "$JID" ] || { echo "remote.sh submit: no job id in sbatch output" >&2; exit 1; }
        # Slurm names the log from the submit file's -o pattern, so derive the
        # repo-relative path the same way the caller would: %j -> the job id.
        # LOGPATTERN lets a caller state it outright when the pattern is unusual.
        REC_LOG=$(printf '%s' "${LOGPATTERN:-}" | sed "s/%j/$JID/g")
    else
        # Bare remote: nothing to hand a job to, so the executor IS the Case B
        # launcher — the same file, shipped over at submit time rather than kept
        # there. Shipping beats installing: a launcher parked on the cluster is
        # one more copy to age out on the next plugin update, and the log header
        # it writes IS the record contract (both SHAs read ON the remote, the PID
        # `queue` matches in /proc, the exit code the linter reads). It lands in
        # .fixer/ — gitignored runtime state — so the mirror stays clean and
        # `push`'s ff-merge is unaffected. ENTRY=none because the record lives on
        # THIS side: the cluster runs jobs, the local mirror is the record.
        if [ "$#" -lt 3 ]; then
            echo "remote.sh submit: $REMOTE_HOST has no sbatch, so this is a bare remote and" >&2
            echo "  the arguments are the launcher's: <script.py> <gpu_id|cpu> <mem_frac> [args...]" >&2
            echo "  got: $*" >&2
            rm -f "$T"; exit 2
        fi
        LAUNCHER="$(cd "$(dirname "${BASH_SOURCE[0]}")/../skills/hpc-submit/scripts" 2>/dev/null && pwd)/launch_bare_gpu.sh"
        if [ ! -f "$LAUNCHER" ]; then
            echo "remote.sh submit: launcher not found beside this script ($LAUNCHER)" >&2
            rm -f "$T"; exit 1
        fi
        # Content-addressed, and copied only when the remote lacks it. A fixed
        # name is unsafe: scp TRUNCATES its target before writing, and bash reads
        # a script by byte offset AS it runs, so a second submit landing on the
        # name the first submit's launcher is still executing swaps the bytes
        # underneath it. The victim dies mid-file — observed as `exit 2` at the
        # payload's argparse, under a log header showing the correct command
        # line, because the header is echoed before the corruption bites, which
        # is what makes it read as a bad invocation rather than a clobbered
        # launcher. Hashing the CONTENT means concurrent submits of one plugin
        # version agree on one file and copy it at most once, and a version
        # change lands on a different name where it cannot reach a live one.
        # The copy itself goes to a per-submit temp and is renamed into place:
        # rename is atomic, so even the first two submits of a new version
        # cannot show a reader a partial file.
        LSUM=$(shasum -a 256 "$LAUNCHER" 2>/dev/null || sha256sum "$LAUNCHER") || {
            echo "remote.sh submit: cannot hash the launcher ($LAUNCHER)" >&2
            rm -f "$T"; exit 1; }
        LSUM=${LSUM%% *}
        RLAUNCH=".fixer/launch_bare_gpu.$LSUM.sh"
        rssh "mkdir -p '$REMOTE_DIR/.fixer'" || { rm -f "$T"; exit 1; }
        if ! rssh "test -s '$REMOTE_DIR/$RLAUNCH'"; then
            scp "${SSH_OPTS[@]}" -q "$LAUNCHER" \
                "$REMOTE_HOST:$REMOTE_DIR/$RLAUNCH.part.$$" || { rm -f "$T"; exit 1; }
            rssh "mv -f '$REMOTE_DIR/$RLAUNCH.part.$$' '$REMOTE_DIR/$RLAUNCH'" \
                || { rm -f "$T"; exit 1; }
        fi
        # TAG (log stem) and CONFIG (channel-1 freeze) are the launcher's own env
        # contract; forward them so a remote launch names its log exactly like a
        # local one.
        E=""
        [ -n "${TAG:-}" ]    && E="$E TAG=$(printf '%q' "$TAG")"
        [ -n "${CONFIG:-}" ] && E="$E CONFIG=$(printf '%q' "$CONFIG")"
        # A LOGIN shell: ssh's non-interactive one reads no profile, so ~/.local/bin
        # is off PATH and `uv` is not found — the job dies at line 2 with exit 127
        # and the launcher can only report it as "exited within 3s".
        RCMD="cd '$REMOTE_DIR' && ENTRY=none$E bash '$RLAUNCH'$Q"
        T2=$(mktemp)
        if ! rssh "bash -lc $(printf '%q' "$RCMD")" >"$T" 2>"$T2"; then
            cat "$T" "$T2" >&2; rm -f "$T" "$T2"; exit 1
        fi
        cat "$T2" >&2                           # the launcher's own diagnostics
        # The launcher still prints a PID when the job died on the spot (the wrapper's
        # own), so a numeric last line is not proof of life. Its 3-second check is,
        # and handing back a dead job's id would record a corpse as running.
        if grep -q 'exited within 3s' "$T2"; then
            rm -f "$T" "$T2"
            echo "remote.sh submit: the job died immediately on $REMOTE_HOST — nothing recorded" >&2
            exit 1
        fi
        rm -f "$T2"
        # The launcher prints the log as a remote absolute path; the record needs
        # it repo-relative, which is also where `pull` will put it locally. Its own
        # last line is the PID, dropped here so the shared tail below is the only
        # one — this subcommand's contract is exactly ONE trailing job id.
        REC_LOG=$(sed -n "s|^log: $REMOTE_DIR/||p" "$T" | tail -1)
        sed "s|^log: $REMOTE_DIR/|log: |" "$T" | sed '$d'
        # PID from STDOUT alone — the launcher's warnings go to stderr and would
        # otherwise be the last line of a merged stream.
        JID=$(tail -1 "$T"); rm -f "$T"
        case "$JID" in
            ''|*[!0-9]*) echo "remote.sh submit: launcher printed no PID" >&2; exit 1 ;;
        esac
    fi
    # Record at launch, like every other venue. The remote launcher runs with
    # ENTRY=none (the cluster has no record layer — its clone is sparse), so
    # without this the row is owed to a session that may not survive to write
    # it, and a job nobody knows about burns cluster time to a log nobody reads.
    # ENTRY="<node>/<page>: <entry name>"; ENTRY=none for a deliberate probe.
    if [ "${ENTRY:-none}" != none ]; then
        RS="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/record_submit.py"
        [ -f "$RS" ] || RS=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
        [ -f "$RS" ] || RS=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/*/scripts/record_submit.py 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
        if [ ! -f "$RS" ]; then
            echo "remote.sh submit: job $JID@$REMOTE_HOST LAUNCHED but record_submit.py not found —" >&2
            echo "  record it on '$ENTRY' by hand now." >&2
            echo "  Do NOT re-run submit: the job is ALREADY running." >&2
            echo "$JID"; exit 3
        fi
        if [ -f "$RS" ]; then
            RPAGE=${ENTRY%%:*}; RNAME=${ENTRY#*:}; RNAME=${RNAME# }
            if ! python3 "$RS" "$RPAGE" "$RNAME" "$JID@$REMOTE_HOST" \
                    "${REC_LOG:-unknown}" ${BIND[@]+"${BIND[@]}"} >&2; then
                echo "remote.sh submit: job $JID@$REMOTE_HOST LAUNCHED but NOT RECORDED —" >&2
                echo "  add it to '$ENTRY' by hand now; nothing else will notice it." >&2
                echo "  Do NOT re-run submit: the job is ALREADY running." >&2
                echo "$JID"; exit 3
            fi
        fi
    fi
    # Full-list refresh (no --host): the snapshot must stay whole — a one-host
    # rewrite would drop every other host's rows and fake J3s for their jobs.
    "$0" queue >/dev/null 2>&1 || true      # so the board sees it this cycle
    echo "$JID"
    ;;
status)
    echo "project : $PROJ ($BR @ $(git -C "$PROJ" rev-parse --short HEAD))"
    for RH in $LOOP_HOSTS; do
        D=$(host_dir "$RH" 2>/dev/null) || D="(no REMOTE_DIR_$RH declared)"
        DEF=""; [ "$RH" = "$DEFAULT_HOST" ] && DEF=" [default]"
        echo "remote  : $RH:$D (data cap ${REMOTE_DATA_MAX_MB:-50}MB)$DEF"
    done
    for name in $(lib_names); do
        lp=$(lib_path_for "$name" LOCAL)
        [ -n "$lp" ] || lp=$(lib_path_here "$name")
        line="lib     : $name local $(git -C "$lp" rev-parse --short HEAD 2>/dev/null)"
        for RH in $LOOP_HOSTS; do
            HK=$(lib_hostkey "$RH"); rp=$(lib_path_for "$name" "$HK")
            [ -n "$rp" ] || continue
            T=$(mktemp); ssh "${SSH_OPTS[@]}" "$RH" "git -C '$rp' rev-parse --short HEAD 2>/dev/null" </dev/null >"$T" 2>/dev/null
            line="$line | $RH $(cat "$T")"; rm -f "$T"
        done
        echo "$line"
    done
    for f in remote_queue remote_last_pull; do
        if [ -f "$STATE/$f" ]; then
            MT=$(stat -c %Y "$STATE/$f" 2>/dev/null || stat -f %m "$STATE/$f")  # GNU || BSD
            AGE=$(( $(date +%s) - MT ))
            echo "$f: $((AGE/60)) min old"
        else
            echo "$f: (never)"
        fi
    done
    ;;
*)
    echo "Usage: remote.sh setup|push|queue|pull|submit <job args...>|status  [--host <h> first]" >&2
    exit 2
    ;;
esac
