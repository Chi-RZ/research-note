---
name: project-setup
description: Use when starting a NEW research project or bringing an OLD/messy one under the standard framework. Instantiates the canonical layout, shared CLAUDE.md/AGENTS.md contracts and memory, dashboard, Python environment, and conservative src/ + experiments/ migration.
---

# research-note:project-setup

Turn any directory into a project that follows the research framework in the
root agent contract (`CLAUDE.md` and `AGENTS.md` are two views of one file): ONE project monorepo (`src/` + `tests/` + `experiments/` +
`project_memory/` + `wiki/` + a project-side `.claude/`, layers told apart by
commit prefixes), a live dashboard, and a reproducible env. The framework
MACHINERY (skills, hooks, linters, fixer, dashboard generator) ships as the
`research-note` plugin; the project carries only its own bindings.

**The mechanical half is a script** — `scripts/bootstrap_project.py` (Step 2)
does the layout, bindings, hooks, fixer, viewer and gate in one idempotent run.
This skill owns what needs judgment: the roles declaration, the project's
the env pinning, and (organize mode) how existing code maps onto `src/` +
`experiments/`.

**Two modes** (auto-detected in Step 0, or force with an arg):
- `new` — greenfield directory (empty or just a git remote).
- `organize` — existing project with code/data already present (e.g. a flat
  legacy repo). Migration is **conservative and reversible**: `git mv` code,
  **never physically move large data** (symlink in place), archive loose files.

The machinery lives in the `research-note` plugin. The same `skills/`, scripts,
templates and project record are used by Claude and Codex; only their manifests
and hook payload adapters differ. Hooks resolve the active project from their
payload, `$RESEARCH_NOTE_PROJECT_DIR`, or `$CLAUDE_PROJECT_DIR`; scripts hard-fail outside a framework project
(marker = `.claude/framework.json` + `project_memory/`). This skill makes a project
ready for those hooks to fire.

---

## Step 0 — Preflight discovery

Gather facts before changing anything. Print a short findings block.

```bash
PROJ="$(pwd)"; echo "project root: $PROJ"
git remote -v 2>/dev/null | head            # main repo remote (keep it)
command -v sbatch >/dev/null 2>&1 && echo "SLURM" || echo "BARE (no sbatch -> uv run per No-Slurm rule)"
ls -A                                        # existing top-level content
```

Decide **mode**: empty-ish dir → `new`; existing code/data → `organize`.

For `organize`, additionally map the terrain:
- Which dirs are an **importable library** (a package with a stable API,
  internal `from <pkg>...` imports, reused across scripts)? → destined for `src/`.
- Which are **composition** (argparse / hydra `main` / plotting / param choices /
  one-off entry points)? → destined for `experiments/`.
- **Data & logs**: `du -sh <dir>` every data dir. Anything large (>~1 GB) is
  **left in place and symlinked** — never copied/moved.
- Backups / stray `*.out` / `*.log` → archive, don't delete.
- Dependencies: `grep -rh "^import\|^from" --include=*.py | sort -u` and note
  external libs the env must provide (e.g. quantax, quimb, jax).

Confirm the migration mapping with the user before the big moves (a table:
`current → target`). Flag any >1 GB data dir explicitly.

---


## Verify before trusting it — `scripts/doctor.sh`

Bootstrap writes files; doctor checks that the machinery they describe is
actually wired up, and prints the fix for whatever is not: main checkout on the
default branch, githooks installed and `core.hooksPath` set, venv present, fork
pins current, and per remote — ssh, clone, sparse cone, scheduler kind, cluster
facts declared, interpreter parity, environment fingerprint parity.

Run it right after bootstrap, after `--remote` adds a host, after a plugin
update, and whenever something behaves oddly. It is re-runnable by design:
most of what it catches was configured correctly once and drifted later (a
clone predating the sparse default, a githook nobody installed, a fork that
moved past its pin, a package installed on one machine only).

**When a remote is declared, ASK for that cluster's queue placement and write
it into `.claude/hpc.env`** — partition, standing reservation, charge account
(`REMOTE_PARTITION` / `REMOTE_RESERVATION` / `REMOTE_ACCOUNT`; blank is a fine
answer for a cluster that needs none). Ask once, at declaration: the submit
step applies them as sbatch flags, so no submit file has to carry them and none
can forget them. Skipping the question is not neutral — jobs then land in the
cluster's default queue, where a ten-minute job can sit an hour behind everyone
else's work with nothing in the record explaining why.

**Capture the rest of that cluster's facts while the user is telling you them** — scheduler, partition, reservation, account, module loads
— and write the submit template for THAT host then and there. A submit file is
instantiated once and never follows the template afterwards, so the moment of
declaration is the only moment the facts are known and the file is unwritten.
Nothing later can infer that a job should have gone to a group reservation.

## Step 1 — Install the plugin (once per agent on a machine)

```bash
claude plugin marketplace add https://github.com/Chi-RZ/research-note.git
claude plugin install research-note@rzchi
PLUGIN="$(ls -d ~/.claude/plugins/cache/*/research-note/* | sort -V | tail -1)"
```

Codex installs the same core from the same repository. A local checkout is the
normal source while the marketplace is under development:

```bash
codex plugin marketplace add /path/to/<this checkout>
codex plugin add research-note@rzchi
PLUGIN="$(ls -d ~/.codex/plugins/cache/*/research-note/* | sort -V | tail -1)"
```

When this skill is already running, use the plugin root that contains this
`SKILL.md`. After bootstrap, every command can resolve it with
`git config --get research-note.pluginRoot`.

## Step 2 — Bootstrap: one idempotent script does the whole mechanical setup

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD"      # add --dry-run to preview
```

It creates the layout (`src/ tests/ experiments/ project_memory/{nodes,memory/shared,note,objectives}
wiki/`), `git init` if needed, the project-side `.claude/` bindings plus shared
`AGENTS.md` views from the
plugin templates (contracts, `framework.json`, `hpc.env`, `settings.json` with
`enabledPlugins`), the four contract symlinks, githooks + `core.hooksPath`,
`autoMemoryDirectory`, `.gitignore` lines, `_index.md` +
`dashboard.html`, the fixer as a detached daemon (never cron — two schedulers
race on one lock, and `crontab(1)` on macOS is TCC-gated), the editor extensions (qdash + markdown white preview) into every VS
Code extensions dir that exists (`~/.vscode-server/extensions/` and/or
`~/.vscode/extensions/` — a local Mac that has run the `code` CLI has both, and
only the latter is the one its window reads), and finally the acceptance gate
(self-tests + both linters). It prints one line per step and a
`needs attention` summary.

**It never overwrites an existing project file** — a re-run reports `kept`, so
running it again after a plugin update is safe and is how you pick up new
scaffolding. Flags: `--dry-run`, `--no-fixer`, `--no-qdash` (skips the whole
editor-extensions step, not just qdash), `--no-cross-agent`.

**One run configures BOTH agents.** The project side was always dual — an
`AGENTS.md` beside every `CLAUDE.md`, `memory/claude` and `memory/codex` as
compatibility links to `memory/shared`, both skill dirs on one `.agent/skills`.
The MACHINE was not: each
CLI keeps its own marketplace list and its own install pin and neither reads the
other's, so a project bootstrapped from Claude left Codex able to read every
word of the doctrine and unable to run one step of it — the skills are in the
other agent's cache, and `.agent/skills/` holds only what this project has
lifted. The last step closes that: it registers the plugin with whichever of
Claude / Codex is installed and lacks it, from the same marketplace source the
running side came from, and reads the marketplace NAME back from the target
rather than assuming it (the two manifests declare different ones —
`rzchi` on both sides today, but read back rather than assumed). It is idempotent (`kept` when the other side
already has it), never fatal, and `skip`s a machine where the other CLI is not
installed or where the script is being run from a dev checkout instead of a
plugin cache.

**Upgrading all registered projects and both installed agents is one command:**

```bash
PLUGIN="$(git config --get research-note.pluginRoot)"
bash "$PLUGIN/scripts/update_projects.sh" --agents both
```

Bootstrap writes each project into the agent-neutral registry at
`~/.config/research-note/projects.json`; the updater also imports legacy Claude
project rows, so neither CLI owns project discovery. Pass one or more project
paths explicitly to update only those projects. The updater refreshes the
selected native marketplaces, moves their install pins to the invoked package
version, verifies Claude/Codex version and source-commit parity, syncs framework
files, and repoints `research-note.pluginRoot`. In VS Code, Reload Window once
after an extension refresh — the only step no script can take.

Read its output before moving on: any `FAIL`/`WARN` line is a real problem
(missing template, dangling symlink, red gate) and is cheaper to fix now than
after the first page is written.

## Step 3 — The judgment calls the script deliberately leaves to you

**The root contract is FRAMEWORK text and is overwritten on every update.** A
project may append below it, and the updater then leaves the whole file alone —
but that turns an automatic sync into a permanent hand-merge, so append only
what has nowhere else to live: an extra commit prefix, which the `commit-msg`
hook reads from there. Prose about what this project is FOR belongs in
`project_memory/note/`, or in the `Goal` of its first objective, where nothing
overwrites it and the record can cite it.

**`.claude/hpc.env`** — the machine facts nothing can infer: where a cluster
is, and which queue to land in. Purely local work needs none of it; the file
bootstrap writes documents every key in its own comments.

**Seed `project_memory/memory/shared/`** with anything learned in Step 0 (env
quirks, data locations, dependency versions) as one-fact-per-file memories +
`MEMORY.md` index lines. Add domain lesson files only when a real lesson
appears — don't pre-create empty scaffolding.

**`src/INDEX.md`** — the capability index every skill checks first; its
`## Domain libraries` section is what keeps the agent layer from hardcoding
which library a project uses:

```markdown
# src/ Capability Index

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

`project_memory/note/` is the user's own free-form scratch space — no format, no
entry rules, not agent-curated. The active agent reads it for context if asked, but does
not write, edit, reorganize, or delete anything there unless explicitly asked to.

Remotes: **local git only** unless the user asks to create a GitHub repo.


## Step 4 — Main-repo hygiene + the environment contract

**Prefix hook** — one commit = one layer, enforced at commit time:
`git config core.hooksPath .claude/githooks` (the hook ships with the agent
clone).

**`.gitignore`** (monorepo) — keep runtime state and heavy/derived data out.
`wiki/`, `project_memory/` AND `.claude/` are TRACKED (the project bindings are
part of the monorepo, `agent:` prefix); experiment data is not. These are the
lines `bootstrap_project.py` writes, and only when no `.gitignore` exists — an
existing one is project property and is never appended to:
```
.fixer
.venv
__pycache__/
*.egg-info/
experiments/*/logs
experiments/*/data
experiments/*/checkpoint
experiments/*/*/logs
experiments/*/*/data
experiments/*/*/checkpoint
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

**`pyproject.toml`** — src-layout so `src/<pkg>/` stays importable.
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
Two files describing two different stacks is the failure this catches; two files
differing by the one dependency that forced them apart is the intended state.

**Set the consistency up at setup, keep it at submit.** At setup, instantiate on
every side and see both report clean — that is the moment the environments agree
for the first time and it costs one command each. At submit, `remote.sh push`
brings the far side UP first (`uv sync`, `Pkg.instantiate()`) and only then
checks, so a host that is merely behind is repaired rather than reported; what
survives that is a real difference and stops the submit.

A check that cannot establish its premise — no uv or julia on the far side, the
host unreachable — reports `cannot verify` and asks. It never reports a failure
it did not observe.

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
where = ["src"]
```

Then `uv sync`, and verify (BARE server: run directly; Slurm: inside srun):
```bash
uv run python -c "import jax; print(jax.devices())"  # must show CudaDevice
uv run pytest tests/ -x -q
```
Run Python as `uv run python -u ...` everywhere (per root CLAUDE.md).

---

## Step 5 — Migrate (organize mode only) — conservative

Preserve import paths; `git mv` in the **main** repo; symlink big data.

1. **Library → `src/`.** Keep the package name (src-layout preserves
   `import <pkg>`): `git mv <old>/<pkg> src/<pkg>`. Zero code edits needed.
   Add its src-tests to `tests/` mirroring `src/`.
2. **Composition → `experiments/<node>/`.** One folder per node: the frozen
   implementation in `impl/`, and a `<group>/` folder per problem instance its
   algorithm is run on holding `run.py` + `plot_*.py`. Experiment-layer tests →
   `experiments/tests/`.
3. **Data (in place).** `mkdir -p experiments/<node>/<group>/data` then
   `ln -s <abs path to existing data dir> experiments/<node>/<group>/data/<name>`.
   Never move >1 GB dirs.
4. **Archive, don't delete.** `mkdir -p _archive` (tracked — superseded
   material kept verbatim for provenance, like the record's own `_archive/`); move loose
   `*.out`, `*.log`, `out_file/`, `*_bak/` there.
5. Populate `src/INDEX.md` rows for the migrated modules.

Commit in **layered** units (never mix): `src/` move, then `experiments/` move,
then infra (`pyproject.toml` + `.gitignore` + `INDEX.md`). Prefixes: `refactor:`,
`exp(<name>):`, `chore:`.

### A top-level directory the six layers cannot absorb — declare a new layer

The commit-msg hook partitions the monorepo: staged top-level dirs minus the
prefix's allowed set, non-empty rejects. A directory outside
`src tests experiments project_memory wiki .claude` therefore cannot be
committed under any prefix until it is declared — loudly, at commit time, which
is the point: "which layer is this" gets answered explicitly instead of a new
directory drifting into whichever layer's commits happen to touch it.

Answer it in this order:

1. **Fold it in if you can.** Most "extra" directories are an existing layer
   under another name — manuscript material is `wiki/`, analysis output is its
   experiment's `figures/`. Moving it needs no rule change and is the right
   answer more often than it feels.
2. **Otherwise it is a NEW layer with its OWN prefix — one prefix, one
   directory set.** Never widen an existing prefix's set instead (no
   `"wiki": {"wiki", "paper"}`): the layer table's whole value is that a
   prefix names exactly one region of the tree, so `git log --grep` and a
   change's blast radius read straight off the prefix. A prefix touching two
   top-level dirs is the partition starting to dissolve — the cheap widening
   today is the mush someone else debugs later.

Declaring one is three edits in one `agent:` commit (the commit touches only
`.claude/` and the root contract, so the existing rules admit it — no
bootstrap problem):

```python
# .claude/githooks/commit-msg — RULES gains a row, own prefix, own dir
    "agent": {".claude"},
    # <project>-specific layers
    "paper": {"paper"},
```

```
| `paper/` | manuscript and submission material | `paper:` |   <- root CLAUDE.md layer table
```

A live precedent: one project absorbed a legacy multi-repo as `"code": {"code"}`,
`"plot": {"results_plot"}` and siblings — twelve top-level dirs that a blind
template copy would have made uncommittable, which is why `update_projects.sh`
diff-and-ports githooks instead of overwriting: your rows survive a plugin
update, and the plugin's own hook changes get ported INTO your copy by hand.
Adding rows to the root contract has the same consequence — the update reports
it DRIFTED and leaves the merge to you. Both are the designed cost of a
project-shaped tree, not a problem.

Two non-answers: `chore` is not the junk layer (its set is EMPTY, root-level
files only, on purpose), and `SKIP_PREFIX_CHECK=1` is the escape hatch for a
genuine anomaly, not a habit — used routinely it turns the partition off.

---

## Step 6 — Board + fixer (already done by Step 2 — verify, don't redo)

`bootstrap_project.py` started the fixer and installed the editor extensions.
Verify and hand over:

```bash
pgrep -af lint_fixer_daemon               # one loop for this project
ls -l project_memory/dashboard.html       # the board exists
```

Then tell the user the one thing a script cannot do: **Reload Window** in VS
Code (a freshly copied extension only loads on reload), after which
`Open Q Dashboard` is in the Command Palette and the Markdown preview renders
on a white page. The board refreshes itself — the fixer rewrites
`dashboard.html` every cycle and qdash watches the file (it never executes
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
plugin's defaults; all runtime state lives in `<project>/.fixer/` (gitignored).

## Step 7 — The gate (bootstrap runs it; re-run after your Step 3 edits)

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD"   # idempotent: re-runs the gate
```

Setup is **not complete** until it reports zero `FAIL` and the contract
symlinks resolve (a dangling symlink loads as nothing, silently):

```bash
for f in CLAUDE.md experiments/CLAUDE.md project_memory/CLAUDE.md wiki/CLAUDE.md; do
  test -e "$f" && echo "OK  $f" || echo "DANGLING  $f"
done
```

Bare `python3` on purpose: the linters and generators must run with no venv, so
the fixer can call them headless.

## Step 8 — Wrap up

- Commit the monorepo per layer prefix (one commit per layer touched);
  `.claude/` is a LAYER of the monorepo — its changes are their own commit
  under the `agent:` prefix, never folded into another layer's.
- Print a summary: layout created, mode used, data left in place (with sizes),
  env command, plugin install line, dashboard path.
- Next action: open the first node with `research-note:plan`.

## Checklist

Each item names what PROVES it — tick on the evidence, not on the intention.

- [ ] plugin is installed and enabled in each CLI present — `claude plugin list` / `codex plugin list`
- [ ] project marker in place — `test -f .claude/framework.json`
- [ ] four contracts resolve — the `DANGLING` loop in Step 7 prints four `OK`
- [ ] `~/.claude` is not shadowing — no `hooks` key, no `skills/` there
- [ ] scaffold complete — `src/ tests/ experiments/tests/ project_memory/{nodes,memory/shared,note,objectives} wiki/knowledge` all exist (bootstrap creates every one; node folders arrive later via research-note:plan)
- [ ] `src/INDEX.md` exists with its `## Domain libraries` section filled in (or explicitly "none")
- [ ] every top-level directory is owned by exactly one commit prefix (a RULES row + a root layer-table row for each beyond the standard six)
- [ ] `autoMemoryDirectory` -> `project_memory/memory/shared` in `.claude/settings.local.json`; `memory/{claude,codex}` resolve there
- [ ] `pyproject.toml` + `.gitignore`; `uv sync` done
- [ ] (organize) code migrated, big data symlinked in place, loose files archived
- [ ] editor extensions installed as real copies (not symlinks); user asked to reload window
- [ ] lint-fixer up — re-running `start_fixer_daemon.sh` prints `already running`, and `doctor.sh` reports the last cycle under thirty minutes old
- [ ] **the gate (Step 7): bootstrap reports zero `FAIL`, and the four contract symlinks print `OK`**
- [ ] `uv run python -c "import <pkg>"` succeeds
- [ ] layered commits (`memory:` / `wiki:` / `chore:` …, `agent:` separately); summary printed; `research-note:plan` suggested
