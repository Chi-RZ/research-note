# Reference — what the launchers write and set

## The log header

Every launcher writes this at the top of the log (a `.slurm` template echoes
it; Slurm routes stdout to the log):

```
# Command: <full launch command incl. env vars>
# Cwd: <absolute working directory>
# Timestamp: <ISO 8601>
# Environment: locked by uv.lock
# <project>: <git SHA> (clean|dirty)
# <lib name>: <git SHA> (clean|dirty)     ← one per .research-note/editables/<name> slot
# Config: <path to frozen yaml, or none>  ← channel 1: the run's parameters
# job_id: <SLURM_JOB_ID + node>          ← Slurm
# PID wrapper: <pid>                     ← bare host: the job id
# PID uv: <pid> / # PID python: <pid>    ← bare host: debug only
# Exit code: running                     ← flipped on exit (Slurm echoes it at the end)
# --- dirty diff (submitted script; empty when clean) ---
<git diff HEAD -- <script>>
# ---
```

The SHAs pin the code (`git show <sha>:<path>` survives rebases); the frozen
yaml or the command line pins the parameters. A long dirty diff means
uncommitted work is running — commit it.

## The GPU environment

Both the GPU `.slurm` template and the bare launcher export:

```bash
export XLA_FLAGS="--xla_gpu_shard_autotuning=false --xla_gpu_experimental_enable_fusion_autotuner=false --xla_gpu_enable_triton_gemm=false"
export JAX_COMPILATION_CACHE_DIR=$HOME/jax_cache
export JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS=10
```

The flags stop XLA's autotuners from benchmarking kernels on fresh
operand-sized buffers, which runs out of memory at compile time on arrays near
the card's size. That failure reads as `RESOURCE_EXHAUSTED` during the first
compilation, before any iteration, with autotuning in the traceback; a larger
memory fraction does not fix it. `--xla_gpu_autotune_level=0` fixes it too but
makes sampling about ten times slower. The cache makes a sweep compile once.
