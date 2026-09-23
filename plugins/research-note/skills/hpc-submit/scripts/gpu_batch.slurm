#!/bin/bash
# GPU batch template (Slurm). Do NOT edit this original: copy it into
# experiments/<node>/<group>/submit/, fill the <placeholders>, then submit per
# SKILL.md Case A — -J/-o/-e on the sbatch command line, params via --export.
#SBATCH --partition=<gpu_partition>
#SBATCH --gres=gpu:<type>:<count>   # or --gpus-per-node=<count> — check YOUR cluster (sinfo -o '%P %G')
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=<cpus>   # estimate from sacct of a similar job (SKILL.md A2)
#SBATCH --mem=<mem>              # ~1.5-2x MaxRSS of a similar job, e.g. 32G
#SBATCH --time=<HH:MM:SS>
# Queue placement comes from .claude/hpc.env (REMOTE_PARTITION /
# REMOTE_RESERVATION / REMOTE_ACCOUNT), applied by the submit step as sbatch
# flags — declared once per machine rather than copied into every submit
# file, where the copy that forgets it queues in the public partition and
# nobody notices until the job has waited an hour.

SCRIPT=run.py
# Channel 2 (argparse): map every --export var to a CLI flag.
ARGS="--D ${D:-64}"
# Channel 1 (Hydra pipeline): the submit step froze the config to
# logs/$CONFIG_NAME.yaml and passed CONFIG_NAME via --export; the job reads
# the frozen copy, never the live config/.
[ -n "${CONFIG_NAME:-}" ] && ARGS="-cp $PWD/logs -cn $CONFIG_NAME"

# Slurm's cgroup renumbers the allocated GPUs from 0; scripts read GPU_ID
# and set CUDA_VISIBLE_DEVICES before importing JAX (script contract)
export GPU_ID=0

# JAX GPU environment (SKILL.md General rules):
# autotuner OOM workarounds — do NOT swap for --xla_gpu_autotune_level=0
export XLA_FLAGS="--xla_gpu_shard_autotuning=false --xla_gpu_experimental_enable_fusion_autotuner=false --xla_gpu_enable_triton_gemm=false"
# persistent compilation cache (big win for sweeps)
export JAX_COMPILATION_CACHE_DIR=$HOME/jax_cache
export JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS=10

# Project profile: developed libraries are declared in <project>/.claude/hpc.env
# (sourced from the submit cwd, the project root per SKILL.md) as
# LIB_<name>_LOCAL / LIB_<name>_<HOSTKEY> lines — one committed file serves
# every machine; this template reads whichever column resolves here (contract:
# templates/hpc.env; canonical functions: scripts/lib_paths.sh — copied
# verbatim because the cluster holds only the repo). A declared lib that
# resolves nowhere writes a WARNING header line rather than vanishing. Legacy
# DOMAIN_LIBS / DOMAIN_LIB_DIR are honoured when no LIB_* is declared.
[ -f .claude/hpc.env ] && . .claude/hpc.env
[ -f .claude/hpc.local.env ] && . .claude/hpc.local.env

# >>> lib_paths (keep every copy of this block identical) >>>
lib_names() {  # every declared <name>, once, one per line
    local v n seen=" "
    for v in "${!LIB_@}"; do
        n=${v#LIB_}; n=${n%_*}
        case "$n" in CHECKOUTS) continue ;; esac   # legacy bump_lib map, not a lib
        case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
    done
}
lib_path_here() {  # <name> -> the first declared path that exists on THIS machine
    local v suffix
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
dirty() { [ -z "$(git -C "$1" status --porcelain)" ] && echo clean || echo dirty; }

# --- standard log header (SKILL.md) ---
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
ENV_DECL=$(rn_read_env "$PWD")
ENV_MANAGER=$(printf '%s\n' "$ENV_DECL" | sed -n 1p); ENV_MANAGER=${ENV_MANAGER:-uv}
[ -n "${RUNNER:-}" ] || RUNNER=$(printf '%s\n' "$ENV_DECL" | sed -n 2p)
RUNNER=${RUNNER:-uv run --no-sync python -u}
echo "# Command: $RUNNER $SCRIPT $ARGS"
echo "# Cwd: $PWD"
echo "# Timestamp: $(date -Is)"
echo "# $(basename "$PWD"): $(git rev-parse --short HEAD) ($(dirty .))"
LIB_DECLARED=$(lib_names)
for name in $LIB_DECLARED; do
    if p=$(lib_path_here "$name"); then
        if lib_sha=$(git -C "$p" rev-parse --short HEAD 2>/dev/null); then
            echo "# $name: $lib_sha ($(dirty "$p"))"
        else
            echo "# $name: WARNING not a git checkout ($p)"
        fi
    else
        echo "# $name: WARNING declared in hpc.env but no LIB_${name}_* path exists on this machine"
    fi
done
[ -z "$LIB_DECLARED" ] && for lib in ${DOMAIN_LIBS:-${DOMAIN_LIB_DIR:-}}; do
    if lib_sha=$(git -C "$lib" rev-parse --short HEAD 2>/dev/null); then
        echo "# $(basename "$lib"): $lib_sha ($(dirty "$lib"))"
    else
        echo "# $(basename "$lib"): WARNING path does not resolve on this machine ($lib)"
    fi
done
# Pinned fork revisions (from uv.lock) + installed-package fingerprint.
# Inlined rather than calling a plugin script: this runs on the cluster,
# which holds only the repo.
[ -x .venv/bin/python ] && .venv/bin/python - . <<'PYFP' 2>/dev/null
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
echo "# Config: ${CONFIG_NAME:+logs/$CONFIG_NAME.yaml}${CONFIG_NAME:-none}"
if [ "$ENV_MANAGER" = uv ]; then
    echo "# Environment: locked by uv.lock"
else
    echo "# Environment: NOT locked — environment.manager is \"$ENV_MANAGER\"; this run records its environment, but nothing guarantees it can be rebuilt"
fi
echo "# job_id: $SLURM_JOB_ID on $SLURM_JOB_NODELIST"
echo "# --- dirty diff (tracked files; empty when clean; capped 64KB) ---"
git diff HEAD -- "$SCRIPT"
echo "# ---"

srun $RUNNER "$SCRIPT" $ARGS
echo "# Exit code: $?"
