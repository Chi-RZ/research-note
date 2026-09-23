---
name: project-setup
description: Use when starting a new research project or bringing an existing one under the framework. Sets the confirmed directory roles, editable contracts, hooks, environment, and optional integrations; an existing project keeps its layout and declares it.
---

# research-note:project-setup

Turn any directory into one monorepo with confirmed semantic roots, a fixed
`project_memory/` record, project-side `.claude/` bindings, commit layers, a
live dashboard, and a reproducible environment. `CLAUDE.md` and `AGENTS.md`
are two views of the same contract. The framework machinery ships in the
`research-note` plugin and the project carries its configuration and bindings.
Scripts resolve
the project from the hook payload, `$RESEARCH_NOTE_PROJECT_DIR` or
`$CLAUDE_PROJECT_DIR`, and hard-fail outside a framework project (marker:
`project_memory/` + `.research-note/project.json`).

**The mechanical half is a script** — `scripts/bootstrap_project.py` (Step 2)
does the layout, bindings, hooks and gate in one idempotent run. Fixer, remote
HPC, editor support and cross-agent registration are optional features. This
skill owns what needs judgment: the roles declaration and the environment.

**Two starting points, one procedure.** An empty directory gets the default
layout. An existing project keeps its layout: its directories are written into
`roles`, and nothing is moved. Setup never moves, renames or archives a file —
a user who wants the standard layout later does that as an ordinary commit.

---

## Step 0 — Preflight discovery

Gather facts before changing anything. Print a short findings block.

```bash
PROJ="$(pwd)"; echo "project root: $PROJ"
git remote -v 2>/dev/null | head            # main repo remote (keep it)
command -v sbatch >/dev/null 2>&1 && echo "SLURM" || echo "BARE (no sbatch -> uv run per No-Slurm rule)"
command -v uv >/dev/null 2>&1 && uv --version || echo "NO uv"
ls -A                                        # existing top-level content
```

**`NO uv` stops here.** The plugin manages the project's Python environment
with uv and nothing else: the lock is what makes a recorded result rerunnable,
and the launcher runs jobs through `uv run`. Tell the user uv is missing, show
the official installer, and run it only after they say yes — it is their
machine:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then re-check `command -v uv` (a fresh install lands in `~/.local/bin`, which
may need adding to PATH in this shell) before going on. A user who declines
gets `bootstrap_project.py --no-uv`, and is told what it costs: nothing
certifies the environment a result ran in; doctor and every log header say so.

Show the layout decision before running bootstrap. The default mapping is:

| role | default directory | declared in |
|---|---|---|
| reusable libraries | `src/` | `roles.libraries` |
| tests | `tests/` | `roles.tests` |
| experiment code and runs | `experiments/` | `roles.experiments` |
| published knowledge | `wiki/` | `roles.knowledge` |
| the record | `project_memory/` | fixed — schema 1 keeps it there |
| agent bindings | `.claude/` + the other agents' views | fixed |

Only the four declared roles are the user's to change; offering the record or
the bindings as a choice invites a configuration that cannot validate.

For an empty project, show these defaults and ask the user to confirm them. For
an existing project, scan every project-owned top-level folder and propose a
mapping before creating the framework. Identify `.git`, virtual environments,
and tool caches separately as local state. For example:

```text
code, packages   → libraries / source / feat, fix, refactor
spec             → tests / source / feat, fix, refactor
trials, notebooks → experiments / experiments / exp
docs             → knowledge / knowledge / wiki
data             → no framework role / data / data
logs             → no framework role / operations / ops
.venv, .pytest_cache → local state / gitignored
```

Show one row for every folder, with its semantic role when it has one, its Git
layer, and the commit prefix for that layer. Ask the user to confirm or edit
every row. Keep all six base layers: `source`, `experiments`, `record`,
`knowledge`, `agent`, and `root`. The `root` layer supplies `chore:` for a
commit containing only files directly under the repository root. Root files
may also accompany a commit for another layer. `root` does not catch
unassigned directories.

Every version-controlled top-level folder must belong to exactly one Git layer.
A folder may stay in its current location, but it may not remain undeclared.
Put folders with the same kind of history in an existing layer. Give a distinct
kind of content its own layer and prefix. Mark local state explicitly and add
its confirmed patterns to `.gitignore`. After confirmation, write the complete
`roles` and `layers` mapping to `.research-note/project.json`, then run
bootstrap. Do not write either file or run bootstrap before the user confirms
the table.

The confirmed file keeps the rest of the shipped defaults. A custom mapping
looks like this:

```json
{
  "roles": {
    "libraries": ["code", "packages"],
    "tests": ["spec"],
    "experiments": ["trials", "notebooks"],
    "knowledge": ["docs"]
  },
  "layers": {
    "source": {"paths": ["code", "packages", "spec"]},
    "experiments": {"paths": ["trials", "notebooks"]},
    "knowledge": {"paths": ["docs"]},
    "data": {"paths": ["data"], "prefixes": ["data"]},
    "operations": {"paths": ["logs"], "prefixes": ["ops"]}
  }
}
```

Merge these values into `templates/project.json`; retain its `schema`, commit
prefixes, `paths.record`, `layers.record`, `layers.agent`, `layers.root`, and
`features` fields.

For an existing project, survey the tree to fill the roles in:
- an **importable library** (a package with a stable API, internal
  `from <pkg>...` imports, reused across scripts) → `roles.libraries`;
- **entry points and runs** (argparse / hydra `main`, plotting, parameter
  choices) → `roles.experiments`;
- tests → `roles.tests`; papers, notes, a wiki → `roles.knowledge`;
- dependencies: `grep -rh "^import\|^from" --include=*.py | sort -u`, to know
  what the environment must provide.

Confirm the table `directory → role` with the user before bootstrap runs. A
directory that fits no role is handled in Step 5.

---

## Step 1 — Install the plugin (once per agent on a machine)

```bash
claude plugin marketplace add https://github.com/Chi-RZ/research-note.git
claude plugin install research-note@research-tools
PLUGIN="$(ls -d ~/.claude/plugins/cache/*/research-note/* | sort -V | tail -1)"
```

Codex installs the same core from the same repository. A local checkout is the
normal source while the marketplace is under development:

```bash
codex plugin marketplace add /path/to/<this checkout>
codex plugin add research-note@research-tools
PLUGIN="$(ls -d ~/.codex/plugins/cache/*/research-note/* | sort -V | tail -1)"
```

When this skill is already running, use the plugin root that contains this
`SKILL.md`. After bootstrap, every command can resolve it with
`git config --get research-note.pluginRoot`.

## Step 2 — Bootstrap: one idempotent script does the whole mechanical setup

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD"      # add --dry-run to preview
```

For an existing project, this command must run only after the confirmed
`.research-note/project.json` has been written. Bootstrap creates missing role
directories from that file and keeps existing directories and files.

For a new project, add only the integrations the user wants:

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD" \
  --with-fixer --with-editor --with-cross-agent
```

Flags: `--remote HOST:DIR` (repeatable; enables HPC and declares a host),
`--with-fixer`, `--with-hpc`, `--with-editor`, `--with-cross-agent`,
`--dry-run`, `--no-self-tests` (skips the plugin's own test suite in the
acceptance gate — a minute — and keeps the linters; for a caller that has just
run it). The old `--no-fixer`, `--no-qdash` and `--no-cross-agent` spellings
remain supported and persistently disable those features. The choices are
written to `.research-note/project.json`, which later runs and SessionStart
hooks read; a project from before that file existed keeps its previous
behaviour on migration.

**If the user named a cluster, pass it here** — `--remote HOST:DIR`, the ssh
alias and where the project lives on that host; the first is the default.
Declaring it at bootstrap is what reaches the queue-placement question below
and writes the submit template while the facts are in front of you. Added
later it still works, but the moment the user was telling you the facts has
passed. `remote.sh setup` clones FROM the project's `origin`, so a project
with no remote stops there: settle the remote with the user before declaring
a host.

It creates the configured role directories and
`project_memory/{nodes,memory/shared,note,objectives}`, runs `git init` if
needed, and writes the project-side `.claude/` bindings plus shared
`AGENTS.md` views from the plugin templates (contracts, `framework.json`,
`settings.json` with `enabledPlugins`), the contract views, githooks +
`core.hooksPath`, `autoMemoryDirectory`, `.gitignore` lines, `_index.md` +
`dashboard.html`, and the acceptance gate (self-tests + both linters). When
selected, it also starts the fixer as a detached daemon (never cron — two
schedulers race on one lock, and `crontab(1)` on macOS is TCC-gated), installs
the editor extensions (qdash + markdown white preview) into every VS Code
extensions dir that exists (`~/.vscode-server/extensions/` and/or
`~/.vscode/extensions/` — a local Mac that has run the `code` CLI has both, and
only the latter is the one its window reads), creates HPC bindings, or
registers the other agent. It prints one line per step and a `needs attention`
summary.

**It preserves existing project files.** A re-run reports `kept` for ordinary
project files. It may update a managed contract's framework section while
preserving the `## Project-specific rules` section. **A `CLAUDE.md` or
`AGENTS.md` the project already had where a contract view belongs is not kept
beside the contract** — a directory holds one contract, so its text is adopted
into that section (`adopted`) and the path becomes the view (`view`). Two such
files that disagree leave the second in place with a `CONFLICT` line: merging
two texts is the user's call.

**One run configures BOTH agents.** The project side is dual by construction
(an `AGENTS.md` beside every `CLAUDE.md`, `memory/claude` and `memory/codex`
linked to `memory/shared`, both skill dirs on one `.agent/skills`); the
cross-agent step makes the MACHINE dual too: each CLI keeps its own
marketplace list and install pin, so it registers the plugin with whichever
of Claude / Codex is installed and lacks it, from the same marketplace source
the running side came from, reading the marketplace NAME back from the target
rather than assuming it. Idempotent (`kept` when the other side already has
it), never fatal, `skip` where the other CLI is absent or the script runs from
a dev checkout instead of a plugin cache.

Bootstrap writes each project into the agent-neutral registry at
`~/.config/research-note/projects.json`; upgrading every registered project
and both installed agents later is `research-note:update`
(`bash "$PLUGIN/scripts/update_projects.sh"`).

Read the output before moving on: any `FAIL`/`WARN` line is a real problem
(missing template, dangling symlink, red gate) and is cheaper to fix now than
after the first page is written.

### Verify before trusting it — `scripts/doctor.sh`

Bootstrap writes files; doctor checks that the machinery they describe is
actually wired up, and prints the fix for whatever is not: main checkout on the
default branch, githooks installed and `core.hooksPath` set, venv present, fork
pins current, and per remote — ssh, clone, sparse cone, scheduler kind, cluster
facts declared, interpreter parity, environment fingerprint parity.

Run it right after bootstrap, after `--remote` adds a host, after a plugin
update, and whenever something behaves oddly. With no flag it checks the core
and every integration the project enables; a disabled one is listed as not
checked, never reported broken. `--core` is the core alone; `--fixer`, `--hpc`
(`--host h` for one cluster), `--editor`, `--cross-agent` check that
integration whether or not it is enabled. Most of what it catches was
configured correctly once and drifted later (a clone predating the sparse
default, a githook nobody installed, a fork that moved past its pin, a package
installed on one machine only).

**When a remote is declared, ASK for that cluster's queue placement and write
it into `.claude/hpc.env`** — partition, standing reservation, charge account
(`REMOTE_PARTITION` / `REMOTE_RESERVATION` / `REMOTE_ACCOUNT`; blank is a fine
answer for a cluster that needs none). Ask once, at declaration: the submit
step applies them as sbatch flags, so no submit file has to carry them and none
can forget them. Unasked, jobs land in the cluster's default queue, where a
ten-minute job can sit an hour behind everyone else's work with nothing in the
record explaining why.

**Capture the rest of that cluster's facts while the user is telling you
them** — scheduler, partition, reservation, account, module loads — and write
the submit template for THAT host then and there. A submit file is
instantiated once and never follows the template afterwards, so the moment of
declaration is the only moment the facts are known and the file is unwritten.

## Step 3 — The judgment calls the script deliberately leaves to you

**The four contracts have two parts.** The framework template comes first.
Project-specific rules go below the `## Project-specific rules` heading in the
same contract. Claude reads the `CLAUDE.md` view and Codex reads the matching
`AGENTS.md` view — one file, two names; a project's own `CLAUDE.md` that was
adopted at setup is now that section, so look there for what it said. Updates replace only the framework section and preserve the
project section. Write there only what has nowhere else to live: a convention
the linters cannot check, a binding to this project's tools. A commit prefix is
a layer in `.research-note/project.json`, not prose. Prose about what this
project is FOR belongs in `project_memory/note/`, or in the `Goal` of its first
objective, where the record can cite it. A rule that would serve every project
belongs in the plugin's template — say so.

**`.claude/hpc.env`** — the machine facts nothing can infer: where a cluster
is, and which queue to land in. Purely local work needs none of it; the file
bootstrap writes documents every key in its own comments.

**Seed `project_memory/memory/shared/`** with anything learned in Step 0 (env
quirks, data locations, dependency versions) as one-fact-per-file memories +
`MEMORY.md` index lines. Domain lesson files arrive when a real lesson does.

**`<first library root>/INDEX.md`** — the capability index every skill checks
first; its
`## Domain libraries` section is what keeps the agent layer from hardcoding
which library a project uses:

```markdown
# Capability Index

One row per module. Search this BEFORE writing new code (see root CLAUDE.md
Discovery rule). `research-note:lift` adds rows here when promoting a capability.

## Domain libraries

| Library | Import | Source to grep | What it covers |
|---------|--------|----------------|----------------|
| <lib> | `import <pkg>` | `<path>` | <what you must NOT re-implement> |

## Modules

| Module | API | What it does |
|--------|-----|--------------|
```

`project_memory/note/` is the user's own free-form scratch space — no format,
no entry rules, not agent-curated. The agent reads it for context if asked and
writes there only when explicitly asked to.

Remotes: **local git only** unless the user asks to create a GitHub repo.

## Step 4 — Main-repo hygiene + the environment contract

**Prefix hook** — one commit = one layer, enforced at commit time. Bootstrap
installs it through `scripts/githooks_install.py`: `.claude/githooks/` holds a
dispatcher, every standard hook name links to it, and `core.hooksPath` points
there. **The hooks the project already had keep running** — the dispatcher
runs research-note's check first, then forwards the event to `.git/hooks/` (or
to the `core.hooksPath` that was set before, remembered as
`research-note.previousHooksPath`) with arguments, stdin and exit code intact.
So a pre-commit framework or git-lfs that was installed BEFORE setup is safe;
one installed AFTER must go into `.git/hooks/` by hand (`pre-commit install`
refuses while `core.hooksPath` is set; `git lfs update --manual` prints the
lines) — the dispatcher picks it up at the next event with no re-install.
`githooks_install.py uninstall PROJECT` puts everything back.

**`.gitignore`** (monorepo) — keep runtime state and heavy/derived data out.
The configured knowledge roots, `project_memory/`, and `.claude/` are tracked;
experiment data is not. `bootstrap_project.py` writes the following patterns
for every configured experiment root, and only when no `.gitignore` exists. An
existing file belongs to the project and is left alone.
```
.fixer
.venv
__pycache__/
*.egg-info/
<experiment-root>/*/logs
<experiment-root>/*/data
<experiment-root>/*/checkpoint
<experiment-root>/*/*/logs
<experiment-root>/*/*/data
<experiment-root>/*/*/checkpoint
```

Slash-LESS on purpose (except the two pure-directory patterns): `dir/`
matches only real directories, so a worktree symlink at the same path is
TRACKED — `git add -A` then captures it, and a later ff-merge deletes the
symlink with the real contents behind it (measured cost: 105 GB). The
slash-less form matches both.
One more rule belongs to the board rather than to the project: a nested
`project_memory/.gitignore` holding `dashboard.html`. The board is rewritten
every fixer cycle, so tracking it buries the entries that say something under a
minified-JSON diff every ten minutes. `gen_dashboard.py` writes that nested file
itself when absent — which is why it is not in the list above. A project that
already TRACKS the board needs `git rm --cached project_memory/dashboard.html`
once; the ignore rule alone does not untrack it.

(Adapt to what already exists; never un-ignore real data.)

**`pyproject.toml`** — point package discovery at the confirmed library root.
**uv is the environment, checked in Step 0.** The unsupported `--no-uv` escape
(declared later with `project_config.py set-environment other [--runner "<cmd>
-u"]`) skips everything below that says uv: doctor warns instead of checking
`.venv`, the cluster's environment comparison is skipped, and every log header
says the environment is NOT locked.

**Every project gets its OWN uv-managed environment** (`.venv/` created by
`uv sync`) — never point the project at a shared pre-existing venv. The venv
is per MACHINE, never synced: it holds architecture-bound binaries, so each
host (laptop, GPU server, cluster) builds its own from the same
`pyproject.toml` + `uv.lock`. What crosses machines is the recipe, not the
build. Consequently batch/recorded runs use `uv run --no-sync` (see
research-note:hpc-submit) — a syncing run rewrites `uv.lock` on any host whose
checkout depth differs, dirtying the clone and the log headers' SHA anchor.
(`[tool.uv] managed = false` aimed at a shared pyenv is legacy-adoption
glue only; convert to a managed env at the first opportunity.)

### The environment contract — one spec, every machine instantiates it

A spec file in the repo describes the environment, and each machine reconstructs
its own from that file. **No machine is ever compared against another.** Platform
variation lives inside the packages — wheels chosen by markers, JLL artifacts
chosen by architecture — so ONE spec resolves correctly everywhere, and what
still differs (BLAS backend, CUDA, CPU arch) is written into the log header
rather than aligned.

| language | spec file (committed) | each machine runs | drift shows as |
|---|---|---|---|
| Python | `uv.lock` + `pyproject.toml` | `uv sync` | `uv sync --check` |
| Julia | `Manifest.toml` + `Project.toml` | `Pkg.instantiate()` | a dep whose `source` is missing |

Two checks, and only two:

- **Each machine matches its own spec**, checked where the job runs. This is
  what makes a recorded result re-derivable, and it needs no second machine.
- **If you are DEVELOPING a library the project uses**, its identity is a
  commit, not a version string — a version stays put across a fortnight of
  edits. Two ways to hold that, and neither is the default: pin it in the spec
  (`{ git = "…", rev = "<sha>" }`, moved by `scripts/bump_lib.sh`), which any
  machine can rebuild from; or keep it path-editable so edits take effect at
  once, and declare `LIB_<name>_LOCAL` / `LIB_<name>_<HOSTKEY>` in
  `.claude/hpc.env` so `remote.sh push` holds both sides to one commit per
  launch. A path dep ties the manifest to one machine's layout, so a pin is
  what a second machine or a CI box needs. Most projects develop no library and
  need none of this.

**A SECOND environment is allowed, and it must strictly contain the first.** One
dependency that exists on only one platform is enough to make a single file
unusable — MKL has no aarch64 build, so a shared Manifest carrying it fails to
instantiate on a Mac. So a variant may exist and may only ADD: every package of
the base appears in it at the same version. That containment is checked
file-to-file in git, needing no host and no network, on every doctor run and
every push (`JULIA_PROJECT` + `JULIA_PROJECT_VARIANTS` in `.claude/hpc.env`).

**Set the consistency up at setup, keep it at submit.** At setup, instantiate on
every side and see both report clean — that is the moment the environments agree
for the first time and it costs one command each. At submit, `remote.sh push`
brings the far side UP first (`uv sync`, `Pkg.instantiate()`) and only then
checks, so a host that is merely behind is repaired rather than reported; what
survives that is a real difference and stops the submit. A check that cannot
establish its premise — no uv or julia on the far side, the host unreachable —
reports `cannot verify` and asks.

Rules that survive that contract:

- **Pin the full dependency list** to exact versions taken from a known-good
  env (`uv pip list` on the reference env) — reproducible, not loose ranges.
- **CUDA jax**: pin `jax-cuda12-plugin[with-cuda]` and `jax-cuda12-pjrt` to
  the EXACT jax version — plain `jax[cuda12]` leaves the plugin range loose
  and can silently fall back to CPU.
- `.venv/` in `.gitignore`; commit `uv.lock`. Julia: commit both tomls, and
  keep the environment OUT of the cluster's sparse cone if the cluster
  maintains its own copy — then a mirror in the repo is refreshed by copying
  the two files back, never by resolving twice.

```toml
[project]
name = "<project>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "numpy==<pin>", "h5py==<pin>", "hydra-core==<pin>",
  "jax==<pin>", "jax-cuda12-plugin[with-cuda]==<jax pin>",
  "jax-cuda12-pjrt==<jax pin>",  # adapt from the reference env
]

# Only if you DEVELOP a library this project uses — see the environment
# contract above for the two ways to hold it, and skip this block otherwise.
# [tool.uv.sources]
# mylib = { git = "ssh://git@github.com/user/mylib.git", rev = "<sha>" }

[tool.setuptools.packages.find]
where = ["<library-root>"]
```

Then `uv sync`, and verify (BARE server: run directly; Slurm: inside srun):
```bash
uv run python -c "import jax; print(jax.devices())"  # must show CudaDevice
uv run pytest <test-root>/ -x -q
```
Run Python as `uv run python -u ...` everywhere (per root CLAUDE.md).

---

## Step 5 — An existing project keeps its layout

A project that keeps its library in `code/`, its tests in `spec/` or its runs
in `trials/` declares those roots — `roles` in `.research-note/project.json`,
each root owned by exactly one layer. Every consumer reads the declaration: the
commit-msg partition, the pre-commit index gate, `gen_index.py`, the N2
cross-check, doctor, the sparse clone and worktree patterns, `remote.sh pull`.
Confirm `python3 "$PLUGIN/scripts/project_config.py" validate` passes and
re-run bootstrap so the layout, contract views and `.gitignore` follow the
declared roots. Import paths stay as they are — nothing moved.

### Account for every top-level directory

The commit-msg hook rejects a staged top-level directory that does not belong
to the commit prefix's layer. Setup must therefore account for every
version-controlled top-level directory before it writes the declaration.

Answer it in this order:

1. Put the directory in an existing layer when it has the same change history.
   `paper/` may join `wiki/` in the knowledge layer; `spec/` may join `code/` in
   the source layer. It does not need to move.
2. Create a layer and prefix when the directory has a distinct change history.
   For example, a large tracked dataset may use a `data` layer and `data:`.

Declaring one is one edit in one `agent:` commit — `.research-note/project.json`
gains a layer; the hook reads the file, so the hook itself is never edited and
an update replaces it freely while your layers survive:

```json
"layers": {
  "paper": { "paths": ["paper"], "prefixes": ["paper"] }
}
```

`project_config.py validate` refuses a path or prefix claimed by two layers. A
project still on the pre-declaration hook (a hand-edited `RULES` table inside
`commit-msg`) keeps working — the hook falls back to its built-in table when
no `project.json` exists — and gains the declaration the next time bootstrap
runs.

`root` means files directly under the repository root. A root-only maintenance
commit, such as a change to `.gitignore` or `pyproject.toml`, uses `chore:`.
Root files may accompany another layer's commit, but an undeclared directory
may not. `SKIP_PREFIX_CHECK=1` remains an escape hatch for a one-off anomaly.

---

## Step 6 — Board + optional fixer and editor support

The dashboard is part of the core. If fixer or editor support was selected,
verify and hand it over:

```bash
pgrep -af lint_fixer_daemon               # one loop for this project
ls -l project_memory/dashboard.html       # the board exists
```

Then tell the user the one thing a script cannot do: **Reload Window** in VS
Code (a freshly copied extension only loads on reload), after which
`Open Q Dashboard` is in the Command Palette and the Markdown preview renders
on a white page. The board refreshes itself — every record write
regenerates `dashboard.html`, the fixer also does so each cycle when it runs,
and qdash watches the file (it never executes
framework code, so nothing to break on the next plugin update).

Fallback without qdash: any HTML previewer pointed at
`project_memory/dashboard.html`.

Two prerequisites the fixer is silently useless without:
- **`claude` on PATH.** On a bare VS Code-server box `claude` is only the
  extension's native binary; `run_fixer.sh` resolves it
  (`$CLAUDE_CODE_EXECPATH` → newest
  `~/.vscode-server/extensions/anthropic.claude-code-*/…/native-binary/claude`).
  Nothing to do unless that resolution comes back empty.
- **Workspace trust.** Headless `claude -p` **ignores every `permissions.allow`
  entry until the workspace is trusted**, so the fixer's agents can edit files
  but cannot run `git` / the linters / `sacct`. Set
  `projects["<abs project path>"].hasTrustDialogAccepted: true` in
  `~/.claude.json`.

Tune models / cadence / caps with a `.fixer/config.json` override of the
plugin's defaults; the fixer's own runtime state lives in `<project>/.fixer/`
(gitignored). The record lock and the other core state are NOT there — they are
in `.research-note/state/`, which exists with or without a fixer.

## Step 7 — The gate (bootstrap runs it; re-run after your Step 3 edits)

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD"   # idempotent: re-runs the gate
```

Setup is **not complete** until it reports zero `FAIL` and the contract
symlinks resolve (a dangling symlink loads as nothing, silently):

```bash
for f in CLAUDE.md project_memory/CLAUDE.md; do
  test -e "$f" && echo "OK  $f" || echo "DANGLING  $f"
done
for role in experiments knowledge; do
  python3 "$PLUGIN/scripts/project_config.py" role "$role" | while read -r root; do
    test -e "$root/CLAUDE.md" && echo "OK  $root/CLAUDE.md" || echo "DANGLING  $root/CLAUDE.md"
  done
done
```

Bare `python3` on purpose: the linters and generators must run with no venv, so
the fixer can call them headless.

## Step 8 — Wrap up

- Commit the monorepo per layer prefix (one commit per layer touched);
  `.claude/` is a LAYER of the monorepo — its changes are their own commit
  under the `agent:` prefix, never folded into another layer's.
- Print a summary: layout created or roles declared,
  env command, plugin install line, dashboard path.
- Next action: open the first node with `research-note:plan`.

## Checklist

Each item names what PROVES it — tick on the evidence, not on the intention.

- [ ] plugin is installed and enabled in each CLI present — `claude plugin list` / `codex plugin list`
- [ ] project marker in place — `test -f .research-note/project.json`
- [ ] four contracts resolve — the `DANGLING` loop in Step 7 prints four `OK`
- [ ] `~/.claude` is not shadowing — no `hooks` key, no `skills/` there
- [ ] scaffold complete — every configured role root and `project_memory/{nodes,memory/shared,note,objectives}` exists
- [ ] the first configured library root contains `INDEX.md` with its `## Domain libraries` section filled in (or explicitly "none")
- [ ] every project-owned top-level directory is confirmed as one Git layer or local ignored state; no folder is unassigned
- [ ] `autoMemoryDirectory` -> `project_memory/memory/shared` in `.claude/settings.local.json`; `memory/{claude,codex}` resolve there
- [ ] `pyproject.toml` + `.gitignore`; `uv sync` done
- [ ] if editor support is enabled, extensions are real copies (not symlinks) and the user was asked to reload the window
- [ ] if fixer is enabled, re-running `start_fixer_daemon.sh` prints `already running`, and `doctor.sh` reports the last cycle under thirty minutes old
- [ ] **the gate (Step 7): bootstrap reports zero `FAIL`, and every contract view prints `OK`**
- [ ] `uv run python -c "import <pkg>"` succeeds
- [ ] layered commits (`memory:` / `wiki:` / `chore:` …, `agent:` separately); summary printed; `research-note:plan` suggested
