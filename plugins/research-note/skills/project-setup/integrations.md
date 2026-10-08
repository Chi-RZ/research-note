# Optional integrations

Read the section for each integration the user asked for. None is on by
default; each is a bootstrap flag and a `features` switch in
`.research-note/project.json`.

## Dashboard (`--with-dashboard`)

Enables `features.dashboard` and creates `project_memory/dashboard.html`.
Record writes and fixer cycles refresh it while enabled. `--no-dashboard`
disables generation and refresh without deleting an existing file. Older
projects without this feature key keep their previous dashboard behavior.
Editor support is a separate choice; request both for a live board in VS Code.
If a project already tracks the generated HTML, untrack it with
`git rm --cached project_memory/dashboard.html` and add an ignore rule.

## Cluster (`--remote HOST:DIR`, enables `hpc`)

Pass the host at bootstrap — the ssh alias and where the project lives there;
the first is the default. `remote.sh setup` clones from the project's `origin`,
so a project with no git remote stops there: settle the remote with the user
first.

**Ask for the queue placement and write it into `.claude/hpc.env`** —
`REMOTE_PARTITION`, `REMOTE_RESERVATION`, `REMOTE_ACCOUNT` (blank is a fine
answer for a cluster that needs none). The submit step applies them as sbatch
flags. Unasked, jobs land in the cluster's default queue, where a ten-minute
job can sit an hour with nothing in the record saying why.

**Write that host's submit template while the user is telling you its facts**
— scheduler, partition, reservation, account, module loads. A submit file is
instantiated once and never follows the template afterwards, so this is the
only moment the facts are known and the file unwritten.

Then `doctor.sh --hpc` checks ssh, the clone, the sparse cone, the scheduler,
the declared facts and environment parity.

## Fixer (`--with-fixer`)

A detached background loop that re-runs the linters and flags forgotten work
every ten minutes (never cron — two schedulers race on one lock, and
`crontab(1)` on macOS is TCC-gated). Verify: `pgrep -af lint_fixer_daemon`
shows one loop for this project. Two prerequisites it is silently useless
without:

- **`claude` on PATH.** On a bare VS Code-server box `claude` is only the
  extension's native binary; `run_fixer.sh` resolves it. Nothing to do unless
  that resolution comes back empty.
- **Workspace trust.** Headless `claude -p` ignores every `permissions.allow`
  entry until the workspace is trusted. Set
  `projects["<abs project path>"].hasTrustDialogAccepted: true` in
  `~/.claude.json`.

Tune it with a `.fixer/config.json` override; its runtime state is in
`.fixer/` (gitignored).

## Editor support (`--with-editor`)

Installs the dashboard viewer (qdash) and a white Markdown preview into every
VS Code extensions directory present. Tell the user the one thing a script
cannot do: **Reload Window**, after which `Open Q Dashboard` is in the Command
Palette. The viewer follows every rewrite of `dashboard.html` by itself.

## Both agents (`--with-cross-agent`)

Both project bindings are now prepared by core setup and select the same locked
runtime. This older flag is accepted for compatibility; it no longer installs
or upgrades either agent's user-level plugin. Install each host application
separately, open this project, accept its normal trust prompts, and start a
fresh session. The project's lock names the selector each host should load.
