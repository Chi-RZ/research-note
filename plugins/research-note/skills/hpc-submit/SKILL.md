---
name: hpc-submit
description: Use when launching any background or batch Python job — on a Slurm cluster, on a bare GPU/CPU server, or on a remote cluster over ssh. Handles dispatch, submit scripts, GPU assignment, OOM retry, the log header, start verification and the submit record. A quick foreground debug run needs none of this.
---

# HPC Submit — launch any background job

Pick the case, apply the rules below, then read that case's file — only that
one:

```
command -v sbatch → found:   Case A, a Slurm cluster you are ON   → slurm.md
                  → nothing: .claude/hpc.env declares REMOTE_HOST?
                               yes → Case C, a remote over ssh    → remote.md
                               no  → Case B, this bare server     → bare.md
```

Case C keeps the agent and the record here; the remote only executes, Slurm or
not. What the launchers write and export — the log header, the GPU flags — is
in `reference.md`.

Resolve the plugin and the experiment roots first:

```bash
PLUGIN="${RESEARCH_NOTE_PLUGIN:-$(git config --get research-note.pluginRoot 2>/dev/null)}"
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.codex/plugins/cache/*/research-note/* 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
[ -d "$PLUGIN" ] || PLUGIN=$(ls -d "$HOME"/.claude/plugins/cache/*/research-note/* 2>/dev/null | awk -F/ '{for(i=1;i<NF;i++)if($i=="research-note"){print $(i+1)"\t"$0;break}}' | sort -V | tail -1 | cut -f2)
python3 "$PLUGIN/scripts/project_config.py" role experiments   # <experiment-root>
```

## Rules for every launch

- **A recorded run never syncs the environment.** Launchers run
  `uv run --no-sync`: a plain `uv run` may rewrite `uv.lock`, dirtying the
  clone, and every log header of that run then records the repository as
  `dirty`. Changing the environment is its own act — `uv sync`, outside a job.
- **Formal runs launch from the main checkout** at a main-branch SHA, after
  the code is merged and re-smoked on the merged state. A worktree run is a
  smoke test: foreground, under 30 minutes, unrecorded.
- **Logs** go in `<experiment-root>/<node>/<group>/logs/`:
  `slurm-<short>-<key_params>-%j.out` on Slurm,
  `<script_stem>[-<key_params>]-<YYYYmmdd-HHMMSS>.log` on a bare host.
- **Parameters** travel one of two ways. Channel 1, a Hydra pipeline script:
  no parameters at submission; the draft `config/config.yaml` is frozen into
  `logs/<stem>.yaml` and the job reads that copy. Channel 2, an argparse
  script: plain flags, and the command line in the log header is the record.
- **Check the start after 60 seconds** — Slurm accepts a job that dies at
  import, a bare PID can die at once. Nothing is reported as running before
  that check.
- Touch only jobs you submitted.

## Recording is part of the launch

Every launcher takes the entry the job belongs to and records it itself — the
job id on the entry's `- **Jobs:**` field, the log link under it,
`Status: running`, the phase's Plan line — in the same action, because a job
that ends in seconds would otherwise be invisible to any later check:

```
ENTRY="<node>/<page>: <entry name>"   required; the entry must exist
PHASE=P<n>                            the Plan phase it serves (O<nn>/P<n> when
                                      two active objectives touch the page)
ROLE="<what this entry does for the phase>"
NO_OBJECTIVE=1                        instead of PHASE/ROLE, for a run that serves none
```

A pre-flight refuses the launch when any of these is missing or ambiguous, so
nothing starts unrecordable. Anything worth running in the background is worth
an entry; `ENTRY=none` exists only for the copy `remote.sh` ships to a
cluster, whose clone has no record.

**The job id is the supervisor's**, never the payload's: Slurm's job id, or on
a bare host the launcher wrapper's PID, its last output line. The uv and
python PIDs in the header are debugging information.

**Exit 3 = launched but not recorded.** The job is running; the page could
not be written (edited mid-flight, or the record lock timed out). Nothing
polls for it later, so repair it in the same turn: every line in the field
that owns it — the id on `Jobs:`, the log link indented under it, knobs in
`Recipe:` — and commit through the record bus (`record_sync.sh -m "memory: …"
<page>` in the main checkout). Report the launch as recorded only after that.

Then print one block per job:

```
[submit]
  job_id:     <Slurm job id | wrapper PID>
  experiment: <node>/<group>
  script:     <submit script or launch command, relative>
  params:     <key=val ...>
  log:        <log path, relative to the project root>
  data:       <expected outputs, or TBD>
  status:     submitted
```

## Watch

The session that launched a job watches it. It never keeps the list in its
head: what is outstanding is every entry at `Status: running`, on disk, and
the linter reports **J3** for one whose jobs have all ended — the harvest
signal, the same check for every venue.

1. **A `Monitor` with `persistent: true`**, at most one per objective. Before
   arming, check whether yours already covers this objective — a later launch
   under it is covered the moment its id lands on the entry, so a launch never
   re-arms. Poll every 120–300 s:

   ```bash
   # resolved inside the poll, so a plugin update reaches a live watcher
   PLUGIN="$(git config --get research-note.pluginRoot 2>/dev/null)"
   bash "$PLUGIN/scripts/remote.sh" queue >/dev/null 2>&1   # remote jobs only
   python3 "$PLUGIN/scripts/harvest_check.py" --min-age 0 --for O<nn>
   ```

   `--for O<nn>` scopes it to your objective, re-derived from the record on
   every poll. Another objective's finished jobs are that loop's, and an
   unharvested line repeats every poll. Work under no objective: drop `--for`
   and keep only lines starting `— `.

2. **No Monitor tool?** For a short job, a foreground `sleep 300` and the same
   check, inside the turn. A background shell is killed at about 30 minutes,
   so a background wait loop orphans every job longer than that.

3. **Nothing armed?** The harvest hook lists, every turn, each `running`
   entry that has sat finished and unharvested for a while, tagged with its
   objective. Entries outside your objective's Plan are read-only; picking up
   an orphan needs the user's say-so.

On the wake: re-run the check to see which entry, `remote.sh pull` if it ran
remotely, and analyze it in-session with full context. The Monitor stays
armed while others run. A lost watcher costs latency, never information —
whoever resumes re-derives the same outstanding set from the pages.
