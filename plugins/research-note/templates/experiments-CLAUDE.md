# Experiment Layer

The code a result came from, and how it is invoked. The root contract holds the
doctrine — node identity, where a job may run, what preserves a result; this
file holds the layout and the conventions.

## Layout

```
experiments/<node>/
  impl/            the node's implementation: the callable functions a run
                   script invokes, plus the declaration of which knobs exist —
                   never their values
  <group>/         one folder per problem instance the node's algorithm is run
                   on. Named for that instance by the project, one level deep.
                   A node opens with one group from the start.
    run + plot scripts     committed
    figures/               what a person looks at — committed
    data/                  what you read — not committed, never deleted
    checkpoint/            what you recompute from — not committed, stays here
    logs/                  what the run says — not committed
    config/  submit/       only where a Hydra pipeline or Slurm needs them
```

Inside a group, subfolders divide by kind of artifact, never by a research
variable: no `data_v2/`, no folder per code state. What distinguishes two runs
goes in the output's name, so results the record calls comparable still pool.

A node folder is permanent. Narrative and conclusions live on the record page,
not here — no README, no DEVLOG.

## Writing the code

**`impl/`** declares which knobs exist and never their tuned values. A knob may
carry a default only if it is bound to the structure it came from, never restated
as a literal — a literal drifts, and every old recipe silently changes meaning
under it. Keep the surface thin: a mechanism of any size splits into modules
behind it. Follow whatever form this project already uses; the framework fixes
neither the language nor the file.

**`<group>/run.py`** (or its equivalent) is composition, not a library: it names one
recipe and hands off to `src/`. A sweep needs no new script — the same frozen node
moves to another point through its knobs. `plot_*.py` reads `data/`, writes
`figures/`, and never triggers computation. A plot that spans groups sits at the
node root beside `impl/`, like the node-level page that reports it. Verification
tests live in `experiments/tests/`.

Before writing a helper inline, look in `src/INDEX.md`. If it is general and
missing, `research-note:lift` puts it there first.

## Running

`command -v sbatch` → a Slurm cluster, and never run compute on its login node;
nothing → a bare server.

| | quick smoke, under half an hour | the real run |
|---|---|---|
| **Slurm** | interactive `srun` with the cluster's debug qos — the flags live in `.claude/hpc-submit/` | `hpc-submit` |
| **bare** | `uv run python -u <script>` in the foreground | `hpc-submit` |

Everything in the right-hand column goes through **`hpc-submit`**, which owns
dispatch, GPU assignment and OOM retry, the log header, job-start verification and
the submit record. Nothing else needs to know which venue it is on.

Inside a Slurm allocation, `unset VIRTUAL_ENV` first — an ambient venv shadows the
project's.

## Log names

```
Slurm   logs/slurm-<short>-<key_params>-%j.out      (%j = the job id)
bare    logs/<script_stem>[-<key_params>]-<YYYYmmdd-HHMMSS>.log
```

Written by `hpc-submit`; create `logs/` if it is missing. Every header carries the
repo SHA, the dirty diff, the environment and the machine, so a log describes its
own run even with the record absent.

## Outputs

**`data/` is what you load to READ a result; `checkpoint/` is what you load to
PRODUCE one.** A table of energies is data; the wavefunction it came from is a
checkpoint, however small. Role decides it, not size. Get this right when you name
the file: anything that leaves this machine — pulled off a cluster, quoted on a
page — leaves because it is in `data/`, and a transfer that can only measure bytes
cannot tell the two apart for you.

**Nothing under `data/` is deleted.** The record, not the file, preserves a
result — a page quotes the number — so a rerun may regenerate its own output.
One job per parameter value, one output per value: concurrent runs must never
write the same path, and the varied key and its value belong in the name, so
plot scripts discover runs by globbing rather than from a list kept somewhere
else. A checkpoint is overwritten only by **its own later state** — step 500
replacing step 400 of the same run. Two runs never share a path.

Write results incrementally as the run proceeds, so a plot shows progress without
waiting for the job to end. A **full history** — every snapshot kept rather than
the latest — stays off unless asked for, behind an explicit flag, with the
per-snapshot size stated where someone will see it before enabling. Format and
save period are the experiment's own business.

A JAX script must set `CUDA_VISIBLE_DEVICES` from `GPU_ID` **before importing
jax**:

```python
import os
os.environ["CUDA_VISIBLE_DEVICES"] = os.environ.get("GPU_ID", "0")
import jax
```
