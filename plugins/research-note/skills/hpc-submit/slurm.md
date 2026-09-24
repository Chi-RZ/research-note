# Case A — Slurm cluster (you are ON the cluster)

`$PLUGIN`, `ENTRY`, `PHASE`, `ROLE` and the exit-3 contract are as in
`SKILL.md`.

## A1. Select or create the submit script

Read `<experiment-root>/<node>/<group>/submit/` and find the script whose
`uv run --no-sync python ... run.py` line runs the intended Python script.

- **Same Python script as an existing `.slurm`** → reuse it; add an
  `--export` variable (env var + CLI-flag mapping) only if a new one is needed.
  Parameter values alone never warrant a new submit script.
- **A different Python script** → copy the project's template from
  `.claude/hpc-submit/` (`cpu_batch.slurm` or `gpu_batch.slurm`) into
  `submit/` and fill its `<placeholders>`.

The project's templates in `.claude/hpc-submit/` carry the cluster facts —
partition, `--gres` syntax and GPU types, reservations, module loads. The
plugin's own `scripts/*.slurm` stay pristine and are never submitted. Missing a
fact? `sinfo -o '%P %G'`, `sacct` on an existing job, the cluster docs, or ask
the user, then write it into the project copy once.

**A submit file ages.** It is instantiated once and never follows the
template, and its log header is the record contract. Before reusing one that
predates your last plugin update, diff it against the plugin's
`skills/hpc-submit/scripts/{cpu,gpu}_batch.slurm` and port the header block.

## A2. Size the request and name the log

Estimate `--mem` / `--cpus-per-task` from a completed job of the same type —
over-requesting silently blocks scheduling (`PENDING (Priority)`):

```bash
sacct -j <jobid> --units=G -n -o JobID%18,JobName,State,MaxRSS,Elapsed
```

Scale by the dominant cost parameter (bond dimension, system size) with
1.5–2× margin. No similar job? Probe once at the smallest parameter first.

`-J` carries the key parameters, and the log follows it (keep the user's own
`-J`/`-o` if given):

```
-J <short>-<key_params>
-o logs/slurm-<short>-<key_params>-%j.out
-e logs/slurm-<short>-<key_params>-%j.out
```

## A3. Submit

A channel-1 (Hydra) script: freeze the config before sbatch — the job must
read the frozen copy, not the live file, which stays editable while it queues:

```bash
CFG_NAME=slurm-<jobname>-$(date +%Y%m%d-%H%M%S)
cp config/config.yaml logs/$CFG_NAME.yaml     # then CONFIG_NAME=$CFG_NAME in --export
```

Submit through `submit_slurm.sh` — sbatch, job-id parse, start check and the
record in one action, job id printed last:

```bash
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
    TAG=<key_params> \
    "$PLUGIN/skills/hpc-submit/scripts/submit_slurm.sh" \
    <experiment-root>/<node>/<group>/submit/<script>.slurm --export=ALL,VAR1=val1
```

Exit 3 means the job is already queued; a retry submits a second one.

## A4. Verify it started (60 s)

```bash
sleep 60
STATE=$(squeue -j $JOB_ID -h -o "%T" 2>/dev/null)
[ -z "$STATE" ] && STATE=$(sacct -j $JOB_ID -n -o State%-20 | head -1 | awk '{print $1}')
echo "Job $JOB_ID state after 60s: $STATE"
```

- `RUNNING` / `PENDING` / `COMPLETING` → go on to the post-submit record.
- `FAILED` / `CANCELLED` / `TIMEOUT` / `NODE_FAIL` / `OUT_OF_MEMORY` → stop:
  tail the last 30 log lines and report; the page waits for the user.
- `COMPLETED` already → suspiciously short; read the log before going on.
