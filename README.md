# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A record framework for agent-assisted computational research, for **Claude
Code** and **Codex**. It records numerical results faithfully, and distils
source code and knowledge as the work proceeds.

## What it is for

- A record that ties each result to its code, recipe, machine, and question.

- A page for supervising long runs. The page survives a finished or compacted
  session, and only you close an entry.

- A shared memory and knowledge base for the project.

- A concise layer you can share with collaborators.

## A typical run

You hand over a goal or a plan; the agent runs it and records the results and
the analysis on a page, for you to review and correct.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/typical-run-dark.svg">
  <img alt="Two lanes and two bands. Top, what only you do: hand over a goal, correct it at any step, close it, ask for a lift. Below it, what the agent does: plan, run, analyze, distil, each naming the skills it drives, with an arc returning from analyze to plan where the page decides what runs next. Beneath both, the dashboard showing what is running, unclosed and needing attention; and the fixer with the linters, which fix the procedure and standardise the format of every page." src="docs/typical-run-light.svg" width="100%">
</picture>

## 1. Install

You need one of the two agents. If you use both, install the same repository in
each agent; their plugin caches remain separate.

**Claude Code**

```bash
claude plugin marketplace add https://github.com/Chi-RZ/research-note.git
claude plugin install research-note@research-tools
```

**Codex**

```bash
codex plugin marketplace add https://github.com/Chi-RZ/research-note.git
codex plugin add research-note@research-tools
```

## 2. Configure a project

Open the directory you want to use as a research project. It can be new or
already contain code. Then tell the agent:

> set up this project with research-note

If you also need a cluster or a GitHub remote, mention it in the same request.

That runs the [`project-setup`](plugins/research-note/skills/project-setup/SKILL.md)
skill. The skill does the following.

- checks whether the directory is new or an existing project. An existing
  project either keeps its own layout, declared in `.research-note/project.json`,
  or is organized: reusable code to `src/`, scripts and one-off entry points to
  `experiments/`, large data left where it is, loose output files archived.
- shows the default directory mapping and asks you to confirm it before setup.
  For an existing project it scans every project folder, proposes its role,
  Git layer, and commit prefix, then lets you edit the table. A folder can stay
  where it is, but each one must be assigned to a layer or confirmed as local,
  ignored state before setup continues. The standard layers remain available.
  `root` is the layer for root-level maintenance files and uses `chore:`; it is
  not a fallback for folders that have not been assigned.
- creates the confirmed role directories and the fixed `project_memory/`
  record, and runs `git init` if needed.
- writes the project contracts, settings, and environment files under
  `.claude/`, installs the githooks in front of any hooks the repository already
  has, and adds the needed `.gitignore` entries. Claude reads `CLAUDE.md` and
  Codex reads `AGENTS.md`; both are views of the same contract. The framework
  text comes first, followed by a `## Project-specific rules` section where you
  can write rules for this project. Updates preserve that section. A `CLAUDE.md`
  or `AGENTS.md` the project already had becomes that section, and the file
  becomes the view: one merged contract, never two files instructing one
  directory.
- creates the dashboard and runs the acceptance checks. The fixer, the editor
  extensions, the cluster support and the registration with the other agent are
  integrations: each is enabled only when you ask for it, and the choice is kept
  in `.research-note/project.json`. You can run setup again; ordinary project
  files stay in place and the contract framework section is refreshed safely.

Optional setup choices are:

| Request or flag | Adds |
|---|---|
| `--remote HOST:PATH` | cluster settings and remote job support |
| `--with-hpc` | HPC bindings without declaring a host yet |
| `--with-fixer` | the background fixer |
| `--with-editor` | editor extensions |
| `--with-cross-agent` | registration with the other installed agent |
| `--no-uv` | an environment managed by conda, pip or another tool (see below) |
| `--dry-run` | show changes without writing them |

The same choices can be disabled with `--no-hpc`, `--no-fixer`,
`--no-editor`, or `--no-cross-agent`. A remote host enables HPC automatically.

If you run jobs on a cluster, include its SSH host and project path in the
request, for example `hpc:/scratch/you/myproject`.

Setup asks where jobs should run on that cluster. It records the partition,
reservation, and account in `.claude/hpc.env`, and submissions use those values
later.

It then clones the project onto the cluster without `project_memory/` or the
configured knowledge directories. The record stays in one place. A cluster
must have a git remote so the code can arrive with `git pull`.

**Python environment.** uv is the default and the supported path: its lock
file is what lets a recorded result be rerun in the same environment, and every
environment check is built on it. A project that uses conda, pip or another
tool declares it at setup with `--no-uv`, or later with
`project_config.py set-environment other --runner "<command> -u"`. Everything
else works the same. The cost is stated rather than hidden: doctor warns that
the environment is not locked, the cluster's environment comparison is skipped,
and every job's log header says the environment is not locked, so a reader of
any result knows it may not be rebuildable.

## Updating

Tell the agent:

> update research-note

That runs the [`update`](plugins/research-note/skills/update/SKILL.md) skill.
One command updates the installed agents and every registered project. It does
the following.

- finds projects from the shared registry and older Claude project entries.
- refreshes each installed agent's marketplace and plugin version, then checks
  that Claude and Codex use the same version and source commit when both are
  installed.
- updates project pins, the framework part of each contract, and the hooks.
  The project-specific section in each contract is preserved. `--dry-run`
  prints what would change.
- preserves project-specific settings and merges new permissions, while
  reporting drift in `hpc.env` and `.slurm` files.
- repoints `research-note.pluginRoot`, then runs doctor and both linters.

The command prints what it changed for each project. It does not stage or commit
anything, so review the output and commit the changes yourself.

## What is tested to work

The plugin's own suite (`plugins/research-note/scripts/tests/`) runs a
compatibility matrix against real repositories on every change:

- an empty directory becomes a local-only project: no fixer, no cluster, no
  editor extension, no second agent — and the record, the hooks and doctor
  work there.
- an existing repository keeps its own code layout (`code/`, `trials/`,
  whatever it has) by declaring it in `.research-note/project.json`; nothing
  is moved, and the commit checks apply to the declared directories.
- an existing repository's git hooks — a pre-commit framework, git-lfs, a
  hand-written pre-push — all still run after setup and after update, with
  their arguments, stdin and exit codes intact.
- an existing repository's own `CLAUDE.md` is merged: the framework text first,
  their rules below it, one file read through both agent names.
- a project that manages Python with conda or pip instead of uv runs its jobs,
  passes doctor, and says in every log header that its environment is not
  locked.
- a machine with one agent, or none on PATH, completes setup.
- the fixer and the cluster support are present only when asked for.
- running setup or update a second time changes nothing.

## Migrating a project set up by an earlier version

Run the update once. It writes `.research-note/project.json` with every
integration turned on, which is what the project had. It keeps anything you
had added below a contract's project-rules heading and updates the framework
text above it. Older projects that used `.research-note/rules/` have those
appendices carried into the contract once, and so does a `CLAUDE.md` or
`AGENTS.md` of your own standing where a contract view belongs: its text moves
into the project-rules section and the path becomes the view. It replaces the
git hooks with the dispatcher, and your project's earlier hooks keep running.
The record lock moves out of `.fixer/` into `.research-note/state/`. The
environment stays on uv unless you declare otherwise. Nothing is deleted. The
update prints one `conflict:` line for every file it could not resolve on its
own, with the command to see the difference. A cluster submit file copied by an
earlier version keeps its old run line until you port it; the update names it.

Claude Code currently supports a few more setup and configuration steps than
Codex. Both agents can run jobs and write the research record.

MIT licensed.
