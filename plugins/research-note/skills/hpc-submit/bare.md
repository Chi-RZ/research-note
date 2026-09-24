# Case B — bare GPU/CPU server (no Slurm)

`$PLUGIN`, `ENTRY`, `PHASE`, `ROLE` and the exit-3 contract are as in
`SKILL.md`.

Every launch goes through the plugin's `launch_bare_gpu.sh`, one call per job
— call the plugin's copy, never one copied into the project. It freezes the
config when `CONFIG` is set, writes the log header, exports the GPU
environment, launches detached, and flips `# Exit code` when the job ends. Its
**last output line is the wrapper PID**: the job id for `- **Jobs:**`.

```bash
# channel 1 (Hydra — parameters in the frozen yaml, none on the command line)
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
    CONFIG=<exp>/config/config.yaml TAG=<key_params> \
    "$PLUGIN/skills/hpc-submit/scripts/launch_bare_gpu.sh" <script.py> <gpu_id|cpu> <mem_frac>

# channel 2 (argparse — parameters on the command line; a node's run.py)
ENTRY="peps_sma/heis_tri: peps_sma vs ED on heis_tri 4x4" PHASE=P3 \
    ROLE="the 4x4 point the bound is read at" TAG=L4-D4 \
    "$PLUGIN/skills/hpc-submit/scripts/launch_bare_gpu.sh" \
    <experiment-root>/peps_sma/heis_tri/run.py 0 0.4 --L 4 --D 4
```

It refuses to run from a linked worktree: a worktree's logs die with it. Land
first and launch from main — `scripts/land_and_launch.sh -- <launcher> <args>`
does both under one lock.

## B1. GPU or CPU, and the job list

CPU when the script is CPU-bound, the user asked for it, or no eligible GPU
exists (then say so); otherwise GPU. A sweep is one job per value, sorted
ascending — channel 2 appends `--KEY <v>`; channel 1 writes one config variant
per value and passes each as `CONFIG=`.

## B2. GPU jobs — which card, what share

```bash
nvidia-smi --query-gpu=index,memory.total,memory.free --format=csv,noheader
```

- Only cards with `memory.total >= 40000 MiB`. A user-pinned GPU passes the
  same filter.
- One job per GPU at `mem_frac = 0.9`. Only when jobs outnumber the cards do
  they share: `mem_frac ≈ 0.9/n` for n sharers, the cheapest parameter values
  grouped together.
- The script reads `GPU_ID` and sets `CUDA_VISIBLE_DEVICES` **before**
  importing JAX; the launcher also sets `XLA_PYTHON_CLIENT_MEM_FRACTION` (JAX)
  and `MEM_FRAC` (torch, which allocates lazily and shares more readily).

## B3. CPU jobs

`cpu` in place of the GPU index, `0` as the fraction: the launcher hides every
GPU and skips the memory variables; everything else is identical. Launch no
more concurrent jobs than the box has cores to serve (`nproc`, and the
script's own thread use).

## B4. Verify, and one OOM retry (60 s after launch)

1. `kill -0 <wrapper pid>` per job. Alive → done.
2. A dead GPU job: look for `ResourceExhausted` / `CUDA out of memory` in its
   log.
   - OOM while sharing a card → relaunch exclusive (`0.9`) on the least-loaded
     eligible card, and check again after 60 s.
   - OOM already at `0.9` → it does not fit one card: report, no retry.
   - OOM during the first compilation, before any iteration: the autotuner
     (see `reference.md`) — report it.
   - Dead, not OOM → tail the log, report, stop.
3. A dead CPU job → tail the log, report, stop. A `MemoryError` is the box's
   RAM, the user's decision.

One retry pass only; after that the job is the watcher's.

To stop a job: kill the python PID, then the uv PID (both in the log header);
the wrapper flips the exit code and exits by itself.
