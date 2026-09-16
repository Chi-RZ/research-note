---
name: hpc-submit
description: Use when launching any background or batch Python job through Slurm or a bare GPU/CPU server. Handles dispatch, submit scripts, GPU assignment, OOM retry, provenance headers, start verification, and the structured submit record. Quick foreground debug runs do not need this skill.
---

# HPC Submit — launch any background job

One skill, three environments. Detect first, apply the general rules, then
follow the matching case.

```
command -v sbatch → found:   Case A — Slurm cluster (you are ON the cluster)
              → nothing: .claude/hpc.env declares REMOTE_HOST?
                           → yes: Case C — remote executor over ssh (the agent stays local)
                           → no:  Case B — bare GPU/CPU server
```

Case C keeps the agent and the record LOCAL while jobs run on the remote: code
travels via GitHub, logs and capped data travel back via the fixer's rsync, so
the recording chain still sees one filesystem — the local mirror. **The remote
need not be a Slurm cluster** — a bare GPU box reached over ssh is the same
case. `remote.sh` dispatches on what the REMOTE has, so you do not: `sbatch`
there means submit a job, no `sbatch` means run the Case B launcher there. The
only thing that changes for you is the argument shape (C2).

**Template layering** (who owns what): the plugin's `scripts/*.slurm` are
PRISTINE generic templates — never edited, never submitted. bootstrap copies
them to `<project>/.claude/hpc-submit/`, where the PROJECT fills its cluster
facts once (partition, `--gres` GPU types, reservations, module loads).
Per-experiment submit scripts under `experiments/<node>/<group>/submit/` are
instantiated from the PROJECT copies.

---

## General rules (both cases)

**A recorded run never syncs the environment.** Batch runs invoke
`uv run --no-sync` (the launcher's `RUNNER` default and both `.slurm`
templates): a plain `uv run` may re-resolve the project and REWRITE `uv.lock`,
and any rewrite dirties the clone — after which every log header of that run
records the repo as `dirty`, which is exactly the anchor the header exists to
provide. A job must not mutate the checkout it is being judged from, nor the
environment it shares with every other job on that machine.

The rewrite has more than one cause, so do not condition the rule on any of
them — a lockfile-format change between uv versions is enough on its own. A dep
declared as a path to a SIBLING directory (`{ path = "../mylib" }`) is the
sharpest case: that path is stored relative to the repo root, so the lockfile is
genuinely wrong on a machine laid out differently, and there `--frozen` is not
the fix either — it validates the lock and dies on the same mismatch
("Distribution not found"). A fork pinned by `git`+`rev` has no such exposure,
and `editable = "."` — the project pointing at ITSELF, which every uv project
carries — never did: `.` resolves in any checkout at any depth.

Environment changes are their own act — `uv sync` on that machine,
deliberately, outside a job.

- **Launch venue.** RECORDED (formal) runs launch from the MAIN checkout at
  a main-branch SHA — that guarantees every link and SHA in a
  record resolves on main forever. Worktree runs are smoke/debug only
  (< 30 min foreground, unrecorded). "Ready to run" for experiment code =
  merged into main AND re-smoked green on the merged state: a branch smoke
  only certifies the impl plus the src it branched from, and the merge may
  bring newer src (`fix:`/`refactor:` commits can change behavior even
  though `lift:` is additive).
- **Templates.** `scripts/` beside this SKILL.md holds reference templates.
  The `.slurm` templates get **copied** into
  `experiments/<node>/<group>/submit/` and their `<placeholders>` filled —
  never modify the originals, never run them in place. `launch_bare_gpu.sh`
  takes no placeholders and is invoked directly from where it lives.
- **Log destination**: `experiments/<node>/<group>/logs/` (create if missing).
  - Case A: `slurm-<short>-<key_params>-%j.out`
  - Case B: `<script_stem>[-<key_params>]-<YYYYmmdd-HHMMSS>.log`
- **Log header.** Every log starts with the header block below. Case A: the
  `.slurm` template echoes it (Slurm routes stdout to the log). Case B:
  `launch_bare_gpu.sh` writes it. Never launch without the header.
- **JAX GPU environment** — exported in both the `.slurm` GPU template and
  the bare launcher:

  ```bash
  # Autotuner OOM workarounds (from quantax): the fusion/Triton-gemm
  # autotuners benchmark kernels on freshly-allocated operand-sized buffers,
  # which OOMs at COMPILE time on near-GPU-sized arrays (big Jacobians).
  # Do NOT use --xla_gpu_autotune_level=0 instead: sampling gets ~10x slower.
  export XLA_FLAGS="--xla_gpu_shard_autotuning=false --xla_gpu_experimental_enable_fusion_autotuner=false --xla_gpu_enable_triton_gemm=false"
  # Persistent compilation cache — big win for sweeps (same code, many jobs)
  export JAX_COMPILATION_CACHE_DIR=$HOME/jax_cache
  export JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS=10
  ```

  Autotuner OOM is recognizable: `RESOURCE_EXHAUSTED` during first
  compilation (before any iteration output), traceback mentions autotuning.
  Raising the memory fraction does not fix it — the flags above do.
- **Parameter channels** (convention in `experiments/CLAUDE.md`):
  - *Channel 1 — Hydra pipeline scripts* (`main.py` etc.): take **no**
    parameters at submission. Params are edited in the draft
    `config/config.yaml` (gitignored); submission **freezes** it to
    `logs/<stem>.yaml` (same stem as the log) and the job reads the frozen
    copy via Hydra's `-cp`/`-cn` — never the live file, which stays free to
    edit while the job queues/runs. Sweep = one frozen yaml per job (the
    agent writes the variants).
  - *Channel 2 — argparse scripts* (plot/diag/small runs): plain CLI flags;
    the command line in the log header is the complete parameter record.
- **Verify start after 60 s** (per-case steps below). Slurm accepts jobs
  that die at import; a bare-server PID can OOM instantly. Never record
  success before checking.
- Only touch jobs you submitted. On shared clusters never `find /`.

### Log header block

```
# Command: <full launch command incl. env vars>
# Cwd: <absolute working directory>
# Timestamp: <ISO 8601>
# <project>: <git SHA> (clean|dirty)
# <lib name>: <git SHA> (clean|dirty)     ← one line per LIB_<name>_* declaration
#                                            in <project>/.claude/hpc.env; a
#                                            declared lib resolving nowhere
#                                            writes a WARNING line instead
# Config: <path to frozen yaml, or none>  ← channel 1: the run's parameters
# job_id: <SLURM_JOB_ID + node>          ← Case A
# PID wrapper: <pid>                     ← Case B: the canonical job id
# PID uv: <pid> / # PID python: <pid>    ← Case B: payload, debug info only
# Exit code: running                     ← Case B header (flipped on exit);
                                           Case A echoes it at log end instead
# --- dirty diff (submitted script; empty when clean) ---
<output of: git diff HEAD -- <script>>
# ---
```

Why this design: the SHAs pin the code baseline (`git show <sha>:<path>`
still works after rebases — timestamp→commit lookup does not). Parameters
are pinned by the frozen yaml (channel 1) or the command line itself
(channel 2) — config files are gitignored, so git never records them; the
frozen copies are their record. The script diff captures uncommitted script
edits; normally it is empty because experiments/ code is committed when
ready-to-run (`exp(<name>):` commit rule) — a long diff means you're running
substantial uncommitted work: commit it.

---

## Case A — Slurm cluster (running ON the cluster)

### A1. Select or create the submit script

Read `experiments/<node>/<group>/submit/`. Find the script whose
`uv run python ... run.py` line matches the intended Python script.

- **Same Python script as an existing `.sh`/`.slurm`** → reuse or modify it:
  - all needed `--export` vars handled → reuse as-is, just change values
  - new `--export` var needed → add it (new env var + CLI-flag mapping)
- **Different Python script** → copy the matching template
  (`scripts/cpu_batch.slurm` or `scripts/gpu_batch.slurm`) into `submit/`
  and fill the `<placeholders>`.

Never create a new submit script just because parameter values changed.

**Cluster facts are PROJECT property, never the plugin's**: partition names,
GPU selection syntax (`--gres` vs `--gpus-per-node`) and valid types,
reservations, qos tiers. Discover them once per cluster — cluster docs,
`sinfo -o '%P %G'`, `sacct` on an existing job, or ask the user — and bake
them into the project's `.claude/hpc-submit/` template copies, where every
per-experiment script inherits them.

### A2. Construct the sbatch command

**Estimate `--mem`/`--cpus-per-task` from similar jobs — do not guess.**
Over-requesting silently blocks scheduling (`PENDING (Priority)`). Read a
completed similar job's actual peak:

```bash
sacct -j <jobid> --units=G -n -o JobID%18,JobName,State,MaxRSS,Elapsed
```

Scale by the dominant cost parameter (bond, χ, system size), request
~1.5–2× as margin. Same job type only (an evolve and a measure at the same
bond differ a lot). No similar job? Probe once at the smallest parameter
and read its MaxRSS first.

**Log naming — `-J` is the source of truth for key params:**

```
-J <short>-<key_params>
-o logs/slurm-<short>-<key_params>-%j.out
-e logs/slurm-<short>-<key_params>-%j.out
```

If the user provides `-J`/`-o`, keep them; otherwise construct from the rule.

### A3. Infer expected data files

Read the submit script for output paths (`--measure-npz`, `--snap-dir`,
`npz`/`joblib`/`hdf5` constructions), resolve with the `--export` values.
Ambiguous → `data: TBD`.

### A4. Submit

**Channel-1 scripts: freeze the config BEFORE sbatch** (the queue wait makes
the live file racy — the job must read the frozen copy):

```bash
CFG_NAME=slurm-<jobname>-$(date +%Y%m%d-%H%M%S)
cp config/config.yaml logs/$CFG_NAME.yaml
# then add CONFIG_NAME=$CFG_NAME to --export below (and no param vars)
```

Submit through `scripts/submit_slurm.sh` — the Case A/C mirror of
`launch_bare_gpu.sh`: sbatch + job-id parse + start check + `record_submit.py`
as ONE action, `ENTRY` required, job id printed LAST. It dispatches by itself:
sbatch present → submit here (Case A); no sbatch but `REMOTE_HOST`/`REMOTE_DIR`
in `.claude/hpc.env` → ssh-submit in the cluster clone (Case C) while the
record is written to the LOCAL page, pointing at the repo-relative log the
fixer will rsync back.

```bash
PLUGIN="${RESEARCH_NOTE_PLUGIN:-$(git config --get research-note.pluginRoot 2>/dev/null)}"
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
    TAG=<key_params> \
    "$PLUGIN/skills/hpc-submit/scripts/submit_slurm.sh" \
    experiments/<node>/<group>/submit/<script>.slurm --export=ALL,VAR1=val1
```

**Exit 3 = submitted but NOT recorded** — same contract as the bare-host
launcher: repair the page by hand in the SAME turn.

### A5. Verify the job started (60 s)

```bash
sleep 60
STATE=$(squeue -j $JOB_ID -h -o "%T" 2>/dev/null)
[ -z "$STATE" ] && STATE=$(sacct -j $JOB_ID -n -o State%-20 | head -1 | awk '{print $1}')
echo "Job $JOB_ID state after 60s: $STATE"
```

- `RUNNING` / `PENDING` / `COMPLETING` → proceed to the post-submit record
- `FAILED` / `CANCELLED` / `TIMEOUT` / `NODE_FAIL` / `OUT_OF_MEMORY` →
  **stop**: tail the last 30 log lines, report, do not update the Q page
  until the user decides
- `COMPLETED` already → suspiciously short; tail the log before proceeding

---

## Case B — bare server (no Slurm)

All launches go through `scripts/launch_bare_gpu.sh` (one call per job).
It derives the experiment dir from the script path, freezes the config when
`CONFIG` is set (channel 1), writes the log header, exports the JAX GPU
environment, launches detached, records the wrapper + payload PIDs in the header, and flips
`# Exit code` when the job ends. **Last output line = wrapper PID** — the
canonical job id (the id that goes in `- **Jobs:**`) and the liveness handle.

`ENTRY` is **required** — `"<node>/<page>: <entry name>"`. There is no
unrecorded-launch option, because there is no need for one: a quick test is a
foreground `uv run python -u …` under the < 30 min exemption, and anything
worth backgrounding is worth an entry. (`none` exists for the copy remote.sh
ships to a cluster, whose sparse clone has no record layer to write into; the
record is written on the local side instead.)

**Exit code 3 = launched but NOT recorded.** The job is running (the PID it
printed is real) but `record_submit.py` could not write it to the page.
The pre-flight (`record_submit.py --check`, run by every launcher before the
launch) makes this rare — what remains is a mid-flight page edit or a lock
timeout.
Nothing polls for it later, so fix it in the SAME turn: repair the page, then
add the Jobs row + log link + `Status: running` by hand. Never report a launch
as successful after exit 3.

The launcher is framework code — call the PLUGIN's copy, never a copy inside
the project. Only the `*.slurm` templates are the project's (you fill
partition/gres for your cluster); a launcher copied into `.claude/` goes stale
on every plugin update.

```bash
PLUGIN="${RESEARCH_NOTE_PLUGIN:-$(git config --get research-note.pluginRoot 2>/dev/null)}"
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)

# channel 1 (Hydra pipeline — params via frozen yaml, none on the CLI):
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
    CONFIG=<exp>/config/config.yaml TAG=<key_params> \
    "$PLUGIN/skills/hpc-submit/scripts/launch_bare_gpu.sh" <script.py> <gpu_id|cpu> <mem_frac>

# channel 2 (argparse — params on the CLI; this is what a node's run.py uses):
ENTRY="peps_sma/heis_tri: peps_sma vs ED on heis_tri 4x4" PHASE=P3 \
    ROLE="the 4x4 point the bound is read at" TAG=L4-D4 \
    "$PLUGIN/skills/hpc-submit/scripts/launch_bare_gpu.sh" \
    experiments/peps_sma/heis_tri/run.py 0 0.4 --L 4 --D 4
```

### B1. Choose the path: GPU or CPU

CPU when: the script is CPU-bound, the user asked for CPU, or no eligible
GPU exists (then warn). Otherwise GPU. Job-list construction is shared:
single job = one entry; parameter sweep = one job per value, values sorted
ascending — channel 2: `--KEY <v>` appended to the script args; channel 1:
one config-yaml variant per value (write the variants, pass each via
`CONFIG=`; the launcher freezes each into its job's `logs/<stem>.yaml`).

### B2. GPU jobs — filter and assign

```bash
nvidia-smi --query-gpu=index,memory.total,memory.free --format=csv,noheader
```

- Keep GPUs with `memory.total >= 40000 MiB` — this excludes GPU 3 (DGX
  Display, 4 GB) always. A user-pinned GPU must pass the same filter.
- Default: **one job per GPU, `mem_frac = 0.9`** (exclusive). Only when
  jobs outnumber the eligible GPUs do jobs share a card: `mem_frac ≈ 0.9/n`
  for n sharers (2 → 0.45, 3 → 0.3), and group the smallest parameter
  values together so the cheap jobs are the ones sharing.
- The launcher sets `GPU_ID` (script contract: read it and set
  `CUDA_VISIBLE_DEVICES` **before** importing JAX),
  `XLA_PYTHON_CLIENT_MEM_FRACTION` (JAX) and `MEM_FRAC` (torch — scripts
  call `torch.cuda.set_per_process_memory_fraction`; torch allocates lazily
  so torch jobs can share a GPU more aggressively than JAX).

```bash
TAG=<key_params> launch_bare_gpu.sh <script.py> <gpu_id> <mem_frac> [args...]
```

### B3. CPU jobs

```bash
TAG=<key_params> launch_bare_gpu.sh <script.py> cpu 0 [args...]
```

Same launcher, `cpu` in place of the GPU index: it exports
`CUDA_VISIBLE_DEVICES=""` (hides all GPUs from JAX and torch), skips the
memory-fraction vars, and everything else (header, PIDs, exit code, log
naming) is identical. No GPU filtering or mem_frac assignment applies.
For parallel CPU sweeps the constraint is cores, not VRAM: don't launch
more concurrent jobs than the box has cores to serve (check with `nproc`
and the script's thread usage).

### B4. Verify (both paths) + OOM retry (GPU only, once, 60 s after launch)

1. `kill -0 <wrap_pid>` per job (the printed wrapper PID). Alive → done.
2. Dead GPU job → scan its log for `ResourceExhausted` / `CUDA out of memory`.
   - Autotuner signature (OOM during first compilation)? The launcher's
     XLA_FLAGS should already prevent this — if it still appears, report.
   - OOM while sharing a card (`mem_frac < 0.9`) → relaunch **exclusive**:
     `mem_frac=0.9` on the least-loaded eligible GPU. Wait 60 s.
   - OOM at `mem_frac=0.9` (already exclusive) → the job doesn't fit on one
     card: report, do not retry.
   - Dead, not OOM → tail the log, report, stop.
3. Dead CPU job → tail the log, report, stop. No retry ladder — mem_frac
   is meaningless on CPU; a `MemoryError` means the box ran out of RAM,
   which is a user decision, not a knob.
4. One retry pass only — completion afterwards belongs to the owner watcher
   (post-submit record, step 3).

To stop a bare-server job: kill the python PID, then the uv PID (both are
in the log header); the wrapper flips the exit code and exits on its own.

---

## Post-submit record (both cases, same turn, mandatory)

1. Print one `[submit]` block per job:

   ```
   [submit]
     job_id:     <Slurm JOB_ID | wrapper PID>
     experiment: <node>/<group>
     script:     <relative path to the submit script or launch command>
     params:     <key=val pairs, space separated>
     log:        <resolved log path, relative to project root>
     data:       <expected output paths; or TBD>
     status:     submitted
   ```

2. Update the task page (`project_memory/nodes/<node>/[<group>/]<page>.md`) per
   `project_memory/CLAUDE.md`, which is where the field rules named below live —
   the root contract carries the doctrine and points here, and does not spell
   `- **Jobs:**` at all:
   - append the job id to that entry's `- **Jobs:** <id, id>` field — the id
     must sit ON the field (J6), and the log link rides as an INDENTED
     continuation of that field (E12/E13-legal, exactly what `record_submit`
     writes);
   - every line sits inside the field that owns it (E12): knobs in `Recipe:`,
     the script and log links in the fields, never loose prose between them;
     create the entry (Status/Date/Motivation/Recipe header) if new;
   - set that entry's `Status: running`;
   - commit it through the record bus (`record_sync.sh -m "memory: …" <page>` in the main checkout, or `put -m "…" -b <sha256> <page> <local-copy>` from a worktree) — it lints, takes the shared lock, and commits path-scoped (it runs the linter for you)

   On a bare host `launch_bare_gpu.sh` does all of this itself — it requires
   `ENTRY="<node>/<page>: <entry name>"` and calls `record_submit.py`. Launching
   and recording are one action, because a cell that finishes in seconds would
   otherwise be invisible to any later poll.

   **It also requires `PHASE=P<n>` and `ROLE="<what this entry does for the
   phase>"`**, and the pre-flight refuses to launch without them
   (`NO_OBJECTIVE=1` for a run that serves no phase). A launch comes FROM a
   phase — the Plan is what said to run this — so the binding is known at the
   launch and at no later moment that can be relied on: left to a following
   turn, a job that runs for hours swallows it, and the phase then shows
   nothing under it while an objective-scoped watcher cannot see the entry at
   all. `record_submit` writes the Plan line itself; those two strings are the
   only parts of it a script cannot derive. Ambiguity is reported, never
   guessed: where two active objectives are in play for the page, give the
   objective too, `PHASE=O<nn>/P<n>`.

   **Canonical id contract**: the id in an entry's `- **Jobs:**` field
   belongs to the SUPERVISOR, never the payload — Slurm: the job id; bare
   host: the launcher wrapper's PID (the launcher's last output line).
   Payload PIDs (uv, python) are log-header debug info only. Watcher and
   fixer alike read liveness from this id; on a bare host verify
   `/proc/<pid>/cmdline` still matches the wrapper before trusting
   `kill -0` (PID reuse).

3. **Owner watches — and the record is the watchlist.** The session that
   launched the jobs watches its OWN — at most one watcher per objective,
   scopes disjoint, never one per job — and
   it never keeps that set in its head: what is outstanding is every entry at
   `Status: running`, which is on disk. `check_node_page.py` already derives
   it and probes each id in the right place (bare host: `ps -p` plus a start-time
   reuse guard; local Slurm: `squeue`; anything `<id>@<host>`: the
   `remote.sh queue` snapshot), and reports **J3** for an entry whose jobs
   have all gone terminal. J3 IS the harvest signal — one check covers all
   four venues, so there is nothing venue-specific to write here:

   **How to wait, in order of preference.** A background Bash task is KILLED
   by the harness at ~30 minutes — measured, not guessed: in one session, 10
   of 13 background tasks died at kill times spaced exactly 30 min apart
   (02:11, 02:41, 03:11, …), and the 3 survivors each finished inside 30 min.
   A 12-hour `sleep`-loop waiter in `run_in_background` is therefore DOOMED
   AT LAUNCH; it was this skill's previous advice, and it silently orphaned
   every job that outlived half an hour.

   1. **The `Monitor` tool with `persistent: true`** — no timeout, wakes the
      session on match. **At most ONE watcher per objective, and arming is
      IDEMPOTENT**: before arming, check whether a Monitor of yours already
      covers this scope — a launch NEVER re-arms, because the poll derives
      the outstanding set from the record, so every later submission under
      the same objective is covered the moment its id lands on the entry.
      An objective run loop arms its Monitor at LOOP ENTRY (see the
      objective skill), so inside a loop there is nothing to arm here. Poll
      command, scoped to YOUR objective (unscoped, another session's
      finished job wakes you, and one abandoned `running` entry matches
      instantly, forever):

      ```bash
      # Resolve PLUGIN INSIDE the poll. bootstrap_project.py maintains this
      # provider-neutral binding for both Claude Code and Codex; resolving it
      # here lets an update replace the path while the watcher is alive.
      PLUGIN="$(git config --get research-note.pluginRoot 2>/dev/null)"
      [ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)
      [ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/* 2>/dev/null | sort -V | tail -1)
      # remote jobs: refresh the snapshot in the same poll — J3 reads
      # <id>@<host> liveness from .fixer/remote_queue, a FILE that only
      # `remote.sh queue` (one ssh) refreshes; >30 min old is unusable.
      bash "$PLUGIN/scripts/remote.sh" queue >/dev/null 2>&1
      python3 "$PLUGIN/scripts/harvest_check.py" --min-age 0 --for O<nn>
      ```

      Match found = harvest signal. Poll interval 120-300 s; drop the
      `remote.sh queue` line for local-only jobs.

      Both lines above encode a paid-for lesson. **Resolve `PLUGIN` in the
      polled command**, not once above the loop: a session that resolved it
      at arming polled a frozen version for its whole life, so a fix landing
      mid-run could never reach it — and nothing about the watcher looks
      wrong while that is true.

      **`--for O<nn>` is the scope, and it is computed by the script, not by
      a grep.** A grep can only match a pattern frozen at arming against
      whatever happens to be printed; `--for` re-derives the scope from the
      record every poll. It admits a line on either of two grounds: it
      attributes to YOUR objective (follows the Plan as it grows — new pages,
      new nodes, the moment their entry lines land), or it attributes to
      NOBODY but lives in a node your Plan already works in — the entry
      launched before anyone wrote its Plan line, invisible to any
      objective-keyed match by construction (the launcher also nags about
      exactly that, the turn it happens). Lines attributed to ANOTHER
      objective are dropped: they are some other loop's to harvest, and an
      unharvested line REPEATS every poll — on a node several objectives
      share, matching them is how a watcher floods itself into the
      harness's rate limit and dies. One frozen single-ground scope already
      cost a harvest: an entry finished at 02:05 and was picked up at 09:19,
      behind a Monitor armed, alive and polling every 180 s throughout.
      Standalone work under no objective: `grep '^— '` on the unscoped
      output. Several objectives in one session: one Monitor each, scopes
      disjoint.

   2. **No Monitor tool in the session? A bounded FOREGROUND check** when the
      job is short (a smoke run): `sleep 300` then the same check, inside
      the turn. Never a background loop longer than ~25 min.

   3. **Armed nothing and moved on?** The harvest HOOK is the net: every
      turn, `harvest_check.py` injects a line for each `running` entry whose
      the entry has sat harvestable, unharvested, for `MIN_AGE_MIN` minutes —
      measured from when a hook FIRST SAW it that way (`.research-note/state/harvest_first_seen.json`,
      shared across sessions), not from when the jobs ended: with no session
      running, nothing is watching and the clock has not started —
      forgotten or orphaned, tagged with the objective that links it. It
      cannot be forgotten (wired in `hooks/hooks.json`, not armed per
      session), and it is deliberately SLOW: fresh finishes are the owner's
      Monitor's business, and broadcasting them project-wide from minute
      zero made every bystander session listen along. Entries not on your
      objective's Plan are READ-ONLY when the hook shows them — picking up
      an orphan requires the user's say-so.

   Pre-flight, whichever venue: the harvest code must exist in the linter you
   poll. Grepping a code the linter never emits is an infinite QUIET loop —
   indistinguishable from "still running" — and it has happened (pre-v3
   waiters grepped R2, renamed J3 in 0.13.0, and spun silently). One line
   makes a stale code name fail loudly:

   ```bash
   grep -q "J3" "$PLUGIN/scripts/check_node_page.py" \
       || { echo "WAITER ABORT: harvest code J3 unknown to this linter — re-read the CURRENT hpc-submit skill"; exit 1; }
   ```

   Launched onto several pages? Pass them all — the check takes a list.

   Then: re-run the check to see WHICH entry, **pull the artifacts if the job
   ran remotely** (`remote.sh pull` — the log and any small data land under
   `experiments/**/logs|data/`, where the entry's links already point), analyze
   that one in-session with full context; the Monitor stays armed while
   others run — nothing is re-armed per harvest.

   Everything in that sentence is the owner's job. The fixer rsyncs finished
   logs and capped data back on its cycle — that is how they reach this side at
   all (§C4) — and it analyzes nothing, moves nothing into the record and flips
   no status: an unattended process deciding what a result MEANS is how a number
   arrives with no one able to say what it is. The daemon's whole remaining role
   is to carry files and raise a hand — `attention:` — when a session that owed
   this work has gone silent.

   Two facts make a lost watcher harmless rather than fatal:
   - The harvest hook is the net behind it — a J3 nobody harvests for 15+
     minutes is injected into every turn of every session in the project,
     with no arming at all. A killed Monitor costs minutes, never a result.
   - **On waking, always re-derive from the record; never trust a remembered
     list.** A resumed session, a different agent, or you by hand all compute
     the same outstanding set from the pages, so a lost watcher costs latency,
     never information.

   Fire-and-forget (submit, no waiter) stays legal: the entry sits at
   `running`, J3 surfaces it on the board, and the fixer stamps `attention:`
   on the owning objective once the page has also gone cold.


## Case C — remote Slurm cluster over ssh (no agent runtime on the cluster)

The project declares its cluster in `.claude/hpc.env` (`REMOTE_HOST`,
`REMOTE_DIR`, `REMOTE_DATA_MAX_MB`); the plugin's `scripts/remote.sh` is the
only transport. The cluster is a pure executor: code reaches it via GitHub,
artifacts come back via the fixer's rsync, all analysis stays local.

Several clusters? Declare them ALL (`REMOTE_HOSTS="h1 h2"` plus one
`REMOTE_DIR_<host>` each) — there is no primary/secondary: every listed host
is monitored equally (`queue` and `pull` loop over the list), `REMOTE_HOST` is
only the default when a host is unstated. Target one host with
`remote.sh <cmd> --host <h>` or `REMOTE=<h> submit_slurm.sh ...`; a
non-default host's job is recorded as `<jobid>@<host>` in the entry's
`- **Jobs:**` field (the linter accepts both forms).

### C1. One-time (per project × cluster)

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD" --remote <host>:<dir>
# = writes hpc.env keys + sparse-clones the repo on the cluster from the GitHub
#   origin (cone: src/ tests/ experiments/ .claude/ — the cluster runs jobs and
#   reads .claude/hpc.env for the log header, and never needs project_memory/
#   or wiki/, whose only effect there is to be read as a record and believed).
#   REPEATABLE: one --remote per cluster, the first is the default host;
#   re-running it also applies the cone to a clone made before this default.
```

Then prepare the remote env ON THE LOGIN NODE (allowed: it is not compute) —
`cd <dir> && uv sync`. A fork pinned by `git`+`rev` needs nothing else: uv
fetches that rev from the fork's own remote, so no clone of it lives on the
cluster at all. Only a PATH-editable lib needs one, and then each side's clone
lives wherever that machine keeps it — the two
paths are declared together in the committed `hpc.env`, one line per side:
`LIB_<name>_LOCAL=<path here>`, `LIB_<name>_<HOSTKEY>=<path there>`. (For a
RELATIVE editable source — `{ path = "../mylib" }` — the clone must also sit at
that relative position beside the remote repo, symlink permitted, or `uv sync`
fails there; uv rewrites uv.lock's path fields relative to the repo root, so a
differing repo depth is cosmetic churn — see the no-sync rule above.)
Declaring the lib is what arms the gate: `remote.sh push` holds every declared
lib to the project's own discipline (clean, pushed, SHA-equal across the pair)
before any submit, and refuses when a declared lib lacks a path for a declared
host — an unsynced editable lib is a silent version skew between what you
think you ran and what the cluster ran, and it has happened here.

### C2. Submit

One subcommand, two argument shapes — `remote.sh submit` probes the REMOTE for
`sbatch` and takes the matching branch. Everything before and after the launch
is identical: local worktree must be CLEAN → `git push` → remote ff-pull + SHA
equality check → launch → job id as the LAST line → queue snapshot refreshed. A
dirty worktree refuses to launch: the record rules demand the commit anyway, and
the remote runs exactly the SHA the log header will claim.

**Launching from a worktree.** `launch_bare_gpu.sh` refuses to run in a linked
worktree — a worktree's logs die with it and leave a dangling link on a page
that outlives it. Land first, then launch from main, and do both under one lock
with `scripts/land_and_launch.sh -- <launcher> <args>`: `merge` rewrites the
working tree this launcher reads for its header, so the two steps have to be one
transaction or a header can name a tree that never ran.

**Slurm remote** — the submit script is a project file under
`experiments/<node>/<group>/submit/`, filled from the plugin's `.slurm`
templates; job id = Slurm's.

```bash
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
bash "$PLUGIN/scripts/remote.sh" submit -J <short>-<key_params> \
     -o <logs/...-%j.out> -e <logs/...-%j.out> --export=ALL,D=64 \
     experiments/<node>/<group>/submit/<name>.slurm
```

**Bare remote** (no `sbatch` there) — there is no queue and no `.slurm` file, so
the arguments are the Case B launcher's, and the job id is the wrapper PID,
which `remote.sh queue` reads back out of the log headers the remote wrote (never by scanning the remote's `/proc` — that conflated one launch's three processes with three jobs):

```bash
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
TAG=<key_params> bash "$PLUGIN/scripts/remote.sh" submit \
     experiments/<node>/<group>/run.py <gpu_id|cpu> <mem_frac> [script args...]
```

`TAG` and `CONFIG` are forwarded, so a remote launch names its log exactly like a
local one. The launcher is shipped into the remote's `.fixer/` at submit time
rather than installed there — a copy parked on the cluster is one more thing to
age out, and the header it writes IS the record contract. The remote launcher runs with `ENTRY=none` — the cluster has no record layer,
its clone is sparse — but **`remote.sh submit` records for you on this side**:
set `ENTRY="<node>/<page>: <entry name>"` in the environment, with the same
`PHASE`/`ROLE` binding the local launchers require, and it appends
`<jobid>@<host>`, links the log and flips the entry to running, exactly as the
local launcher does — the pre-flight refuses here for the same reason it
refuses there. A remote submit is the one venue where the job runs on one
machine and its record lives on another, so leaving the row to a session that
may not survive the wait is how a job goes missing entirely. The printed `log:`
line is already repo-relative — use it verbatim in the entry; the file lands
locally on the next `pull` (P2 exempts `logs/` for that window).

**Submit files age.** A `.slurm` under `experiments/<node>/<group>/submit/`
is instantiated from the template ONCE and then never follows it — the log
header the template writes is the record contract, so a file made before the
template gained a field silently produces runs missing that evidence (seen:
runs with no `(pinned)` / `# env:` lines). Before reusing a submit file that
predates your last plugin update, diff it against
`skills/hpc-submit/scripts/{cpu,gpu}_batch.slurm` and port the header block;
the run itself will not complain.

### C3. Record — automatic, same rules as A/B

Job id → the owning entry's `- **Jobs:**` field; full context + the LOG's repo-relative
link inline in the entry. The log path is the SAME relative path as Case A
(`experiments/<node>/<group>/logs/slurm-...-<jobid>.out`) — the file lives on
the cluster first and lands locally on the fixer's next pull (≤10 min), so the
link is briefly dangling; P2 exempts `logs/` for exactly this reason.

### C4. Monitor / retrieve — the owner watches here too

The owner-watch rule does not stop at the ssh boundary: the watcher is the
SAME Monitor as every other venue (its poll already prefixes `remote.sh
queue`, so the snapshot is fresh each probe — the set is derived from the
record, never remembered). On the J3 wake, run `remote.sh pull` yourself and
analyze from the pulled logs — remote.sh is plain transport, callable by any
session, not fixer-only.

The fixer's cycle keeps running the same two commands as the safety net for
orphans and as the background artifact mover: `remote.sh queue` (snapshot →
`.fixer/remote_queue`, which the J3/J4 lint and the board's Running tab read —
a stale snapshot makes the queue read as unusable rather than inventing "job
finished") and `remote.sh pull` (all of `experiments/**/logs/`, plus
`experiments/**/data/` files ≤ `REMOTE_DATA_MAX_MB`). Big artifacts stay on
the cluster by design — an analysis that needs one says so and reads it over
ssh, or raises the cap deliberately.

### C5. Never

- Never run Python on the remote login node (submit only; env prep excepted).
- Never edit the remote working copy in place — it is a pure mirror; a
  diverged remote makes `remote.sh push` refuse until fixed by hand.
- Never scan the cluster filesystem broadly (`find /` etc. hang on HPC mounts).
