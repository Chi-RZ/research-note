---
name: project-setup
description: Use when starting a new research project or bringing an existing one under the framework. Sets the confirmed directory roles, editable contracts, hooks, the uv environment, and optional integrations; an existing project keeps its layout and declares it.
---

# research-note:project-setup

Turn a directory into a research project: confirmed directory roles, the
`project_memory/` record, the instruction files (`CLAUDE.md` and `AGENTS.md`
are two views of one contract), git hooks and a uv environment; the dashboard is optional.
`scripts/bootstrap_project.py` does the mechanical part in one idempotent run;
this skill owns the judgment — which directory is which, and the environment.

**Two starting points, one procedure.** An empty directory gets the default
layout. An existing project keeps its layout: its directories are written into
`roles`, and nothing is moved. Setup never moves, renames or archives a file —
a user who wants the default layout later does that as an ordinary commit.

## Step 0 — Look before changing anything

```bash
PROJ="$(pwd)"; echo "project root: $PROJ"
git remote -v 2>/dev/null | head
command -v uv >/dev/null 2>&1 && uv --version || echo "NO uv"
ls -A
```

**`NO uv` stops here.** The plugin manages the project's Python environment
with uv: the lock is what makes a recorded result rerunnable, and jobs run
through `uv run`. Tell the user uv is missing, show the official installer,
and run it only after they say yes — it is their machine:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then re-check `command -v uv` (a fresh install lands in `~/.local/bin`, which
may need adding to PATH in this shell). A user who declines gets
`bootstrap_project.py --no-uv` and is told what it costs: nothing certifies
the environment a result ran in, and doctor and every log header say so.

## Step 1 — Confirm which directory is which

| role | default directory | declared in |
|---|---|---|
| reusable libraries | `src/` | `roles.libraries` |
| tests | `tests/` | `roles.tests` |
| experiment code and runs | `experiments/` | `roles.experiments` |
| published knowledge | `wiki/` | `roles.knowledge` |
| the record | `project_memory/` | fixed |
| agent bindings | `.claude/` + the other agents' views | fixed |

Only the four declared roles are the user's to change.

**An empty directory:** show these defaults, confirm, go to Step 2.

**An existing project:** survey every top-level directory and propose one row
each — its role, if it has one, its git layer, and that layer's commit prefix:

- an importable library (a package with a stable API, reused across scripts)
  → `libraries`; entry points and runs (argparse / hydra `main`, plotting,
  parameter choices) → `experiments`; tests → `tests`; papers, notes, a wiki →
  `knowledge`;
- a directory with no role still belongs to exactly one **git layer**, because
  the commit hook rejects a staged directory no layer owns. Put it in an
  existing layer when it changes the same way (`paper/` with `wiki/`), or give
  it its own layer and prefix (`data/` → `data:`);
- `.venv`, caches and other local state → `.gitignore`, no layer.

```text
code, packages   → libraries / source / feat, fix, refactor
spec             → tests / source / feat, fix, refactor
trials           → experiments / experiments / exp
docs             → knowledge / knowledge / wiki
data             → no role / data / data
.venv            → local state / gitignored
```

The six base layers stay: `source`, `experiments`, `record`, `knowledge`,
`agent`, and `root` — `root` gives `chore:` to a commit of files directly under
the repository root, and does not catch an unassigned directory.

After the user confirms every row, write the mapping into a copy of
`$PLUGIN/templates/project.json` at `.research-note/project.json`, keeping its
other fields, and check it:

```json
{
  "roles": {"libraries": ["code", "packages"], "tests": ["spec"],
            "experiments": ["trials"], "knowledge": ["docs"]},
  "layers": {
    "source": {"paths": ["code", "packages", "spec"]},
    "experiments": {"paths": ["trials"]},
    "knowledge": {"paths": ["docs"]},
    "data": {"paths": ["data"], "prefixes": ["data"]}
  }
}
```

```bash
python3 "$PLUGIN/scripts/project_config.py" validate
```

Nothing is written and bootstrap does not run before the user confirms.

## Step 2 — Bootstrap

`$PLUGIN` is the plugin root containing this `SKILL.md`; after bootstrap,
`git config --get research-note.pluginRoot` names it.

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD"
```

Use `--dry-run` when the user requests a preview or the proposed changes need
inspection before applying them. The normal path runs bootstrap once.

Add only the integrations the user asked for — each has a section in
[integrations.md](integrations.md), read it for the ones chosen:
`--remote HOST:DIR` (a cluster; repeatable), `--with-dashboard`, `--with-fixer`, `--with-editor`,
`--with-cross-agent`. The choices land in `.research-note/project.json`.

Bootstrap creates the role directories and `project_memory/`, runs `git init`
if needed, writes the `.claude/` bindings and the instruction-file views,
installs the git hooks, pins the complete plugin for both agents in this project,
writes `.gitignore` when none exists, generates
`_index.md` (plus `dashboard.html` when enabled), and ends with both linters as its acceptance
gate. It prints one line per step and a `needs attention` summary; read every
`FAIL`/`WARN` before going on.

It keeps existing project files (`kept`). Two things to know on an existing
project:

- **A `CLAUDE.md` or `AGENTS.md` it already had is merged, not kept beside.**
  Its text becomes the contract's `## Project-specific rules` section
  (`adopted`) and the path becomes the view. Two such files that disagree leave
  the second in place with a `CONFLICT` line — merging them is the user's call.
- **Its git hooks keep running.** The dispatcher runs research-note's checks,
  then forwards each event to the hooks that were active before, arguments and
  exit code intact. A hook tool installed *after* setup goes into
  `.git/hooks/` by hand (`pre-commit install` refuses while `core.hooksPath` is
  set). `githooks_install.py uninstall PROJECT` puts everything back.

Setup preserves an existing `.research-note/plugin-lock.json`; it does not
upgrade a project because the user-level plugin changed. The generated
`.codex/config.toml` and Claude settings select the same immutable runtime.
Host trust prompts still apply. Running sessions keep their loaded version;
Claude can `/reload-plugins`, while Codex loads the pin in a new session.

## Step 3 — The environment

Write `pyproject.toml` with package discovery pointed at the confirmed library
root, dependencies pinned to exact versions, then build and check:

```toml
[project]
name = "<project>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["numpy==<pin>", "..."]

[tool.setuptools.packages.find]
where = ["<library-root>"]
```

```bash
uv sync
uv run python -c "import <pkg>"
uv run pytest <test-root>/ -x -q
```

Every project gets its own `.venv` from `uv sync`, never a shared venv; commit
`uv.lock`. Python always runs as `uv run python -u`.

If the project develops a library of its own, uses Julia, needs a second
platform, or pins CUDA jax, read [environment.md](environment.md) before
writing `pyproject.toml`.

## Step 4 — What only the user can supply

- **Project-specific rules** go below `## Project-specific rules` in the
  matching contract; updates replace only the framework part above it. Write
  there only what has nowhere else to live — a convention the linters cannot
  check, a binding to this project's tools. A commit prefix is a layer in
  `project.json`, not prose; what the project is FOR belongs in
  `project_memory/note/` or its first objective's Goal.
- **`<first library root>/INDEX.md`** — the capability index every skill
  checks before writing code. Its `## Domain libraries` section names the
  libraries the project builds on, so no skill hardcodes one:

  ```markdown
  # Capability Index

  ## Domain libraries

  | Library | Import | Source to grep | What it covers |
  |---------|--------|----------------|----------------|
  | <lib> | `import <pkg>` | `<path>` | <what you must NOT re-implement> |

  ## Modules

  | Module | API | What it does |
  |--------|-----|--------------|
  ```

- **Shared memory** — anything learned in Step 0 worth keeping (an env quirk,
  where data lives) as one-fact-per-file memories in
  `project_memory/memory/shared/`, each with a line in `MEMORY.md`.

`project_memory/note/` is the user's own scratch space: read it when asked,
write there only when asked. The git remote stays local unless the user asks
for a GitHub repository.

## Step 5 — Verify installation once

```bash
python3 "$PLUGIN/scripts/bootstrap_project.py" "$PWD" --check
```

This read-only check verifies the project declaration, contract views, shared
memory and skills, plugin binding and Git hooks. It leaves files, environments
and services untouched. Setup is complete when it exits zero and the earlier
bootstrap reported zero `FAIL`. If a check fails, use `doctor.sh` to diagnose
it, repair the reported problem, then repeat the check. Verify enabled
integrations through their sections in `integrations.md`.

## Step 6 — Commit and hand over

Commit one layer per commit — `.claude/`, `.codex/` and `.research-note/` under `agent:`,
root files under `chore:`, never folded into another layer's commit. Then tell
the user: the roles declared, the environment command, and, if enabled, the
dashboard path (`project_memory/dashboard.html`); what each chosen integration still needs
from them, and that the next step is `research-note:plan`.

## Checklist

Tick on the evidence named, not on the intention.

- [ ] uv present — `uv --version`
- [ ] every top-level directory has a role or a layer, or is ignored; the user confirmed the table — `project_config.py validate`
- [ ] bootstrap reports zero `FAIL`; every contract view prints `OK`
- [ ] `INDEX.md` in the first library root, `## Domain libraries` filled in (or "none")
- [ ] `uv sync` done; `uv run python -c "import <pkg>"` succeeds
- [ ] `bootstrap_project.py PROJECT_DIR --check` exits zero
- [ ] each chosen integration's section in `integrations.md` followed
- [ ] layered commits made; `research-note:plan` suggested
