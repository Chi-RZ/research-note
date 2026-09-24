# Case C — a remote cluster or GPU box over ssh

`$PLUGIN`, `ENTRY`, `PHASE`, `ROLE` and the exit-3 contract are as in
`SKILL.md`.

The agent and the record stay local; the remote only executes. Code reaches it
through the git remote, and `remote.sh` — the only transport — brings logs and
small data back. `remote.sh submit` looks for `sbatch` on the far side:
present, it submits a Slurm job; absent, it runs the bare launcher there.

The cluster is declared in `.claude/hpc.env` (`REMOTE_HOST`, `REMOTE_DIR`,
`REMOTE_DATA_MAX_MB`). Several clusters: `REMOTE_HOSTS="h1 h2"` plus one
`REMOTE_DIR_<host>` each, all watched equally; `REMOTE_HOST` is only the
default. Target one with `remote.sh <cmd> --host <h>`; a job on a non-default
host is recorded as `<jobid>@<host>`.

## C1. Once per project and cluster

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD" --remote <host>:<dir>
```

It writes the `hpc.env` keys and sparse-clones the repository on the cluster,
without `project_memory/` and the knowledge roots — a stale record copy there
is a page someone eventually believes. Then, on the login node (preparing the
environment is not compute): `cd <dir> && uv sync`.

A library the project develops path-editable needs a checkout on each side,
declared together in `hpc.env`: `LIB_<name>_LOCAL=<path here>`,
`LIB_<name>_<HOSTKEY>=<path there>`. `remote.sh push` then holds both to one
clean, pushed commit before any submit. A library pinned by `git` + `rev`
needs nothing — uv fetches that commit. See the project-setup skill's
`environment.md`.

## C2. Submit

Before any launch `remote.sh submit` requires a clean local tree, pushes,
fast-forwards the remote and checks the SHAs match — the remote runs exactly
the commit the log header will name. The job id is the last line.

Slurm on the far side — the submit script is a project file, as in Case A:

```bash
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
bash "$PLUGIN/scripts/remote.sh" submit -J <short>-<key_params> \
     -o <logs/...-%j.out> -e <logs/...-%j.out> --export=ALL,D=64 \
     <experiment-root>/<node>/<group>/submit/<name>.slurm
```

No Slurm on the far side — the arguments are the bare launcher's (Case B), and
the job id is the remote wrapper PID:

```bash
ENTRY="<node>/<page>: <entry name>" PHASE=P<n> ROLE="<what this entry does for the phase>" \
TAG=<key_params> bash "$PLUGIN/scripts/remote.sh" submit \
     <experiment-root>/<node>/<group>/run.py <gpu_id|cpu> <mem_frac> [script args...]
```

`TAG` and `CONFIG` are forwarded, so the log is named as a local one would be.
`remote.sh submit` records on this side: it appends `<jobid>@<host>`, links
the log by the repo-relative path it prints, and sets the entry `running`. The
log arrives on the next pull; until then the link dangles, which P2 allows
under `logs/`.

## C3. Watch and retrieve

The watcher is the same one as every venue (`SKILL.md`, "Watch"); its poll
refreshes the remote queue snapshot. On the J3 wake, run `remote.sh pull`
yourself and analyze the pulled logs. `pull` brings every experiment root's
logs and the data files up to `REMOTE_DATA_MAX_MB`; bigger artifacts stay on
the cluster — read one over ssh, or raise the cap deliberately. A fixer, when
enabled, runs `queue` and `pull` on its cycle as a safety net.

## C4. Never

- Run Python on the remote login node (environment preparation excepted).
- Edit the remote working copy — it is a mirror; a diverged one makes
  `remote.sh push` refuse until fixed by hand.
- Scan the cluster filesystem broadly (`find /` hangs on HPC mounts).
