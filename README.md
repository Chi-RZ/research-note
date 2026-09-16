# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A record framework for agent-assisted computational research, for **Claude
Code** and **Codex**. It records numerical results faithfully, and distils
source code and knowledge as the work proceeds.

## What it is for

- A formatted structure that records computational results faithfully — the
  commit, the recipe, the machine and the question all resolve from the record
  alone.

- A long run you supervise from a page, not from a transcript. Sessions end and
  get compacted; the page is what survives them, and only you close an entry.

- An auto-evolving code memory and knowledge base that grows with your project.
  The agent grows with you.

- An easily shareable distilled layer for collaborating with other people later.

## A typical run

You hand over a goal or a plan; the agent runs it and records the results and
the analysis on a page, for you to review and correct.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/typical-run-dark.svg">
  <img alt="Two lanes and two bands. Top, what only you do: hand over a goal, correct it at any step, close it, ask for a lift. Below it, what the agent does: plan, run, analyze, distil, each naming the skills it drives, with an arc returning from analyze to plan where the page decides what runs next. Beneath both, the dashboard showing what is running, unclosed and needing attention; and the fixer with the linters, which fix the procedure and standardise the format of every page." src="docs/typical-run-light.svg" width="100%">
</picture>

## 1. Install

You need one of the two agents. Installing for both is the same two commands
twice — they share one copy of the plugin, not two.

**Claude Code**

```bash
claude plugin marketplace add https://github.com/Chi-RZ/research-note.git
claude plugin install research-note@rzchi
```

**Codex**

```bash
codex plugin marketplace add https://github.com/Chi-RZ/research-note.git
codex plugin add research-note@rzchi
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
- creates `src/`, `tests/`, `experiments/`, `project_memory/`, and `wiki/`, and
  runs `git init` if needed.
- writes the project contracts, settings, and environment files under
  `.claude/`, installs the githooks in front of any hooks the repository already
  has, and adds the needed `.gitignore` entries. Claude reads `CLAUDE.md` and
  Codex reads `AGENTS.md`; both are views of the same contract. The framework
  text comes first, followed by a `## Project-specific rules` section where you
  can write rules for this project. Updates preserve that section.
- creates the dashboard and runs the acceptance checks. The fixer, the editor
  extensions, the cluster support and the registration with the other agent are
  integrations: each is enabled only when you ask for it, and the choice is kept
  in `.research-note/project.json`. The setup can be run again without
  overwriting existing project files.

If you run jobs on a cluster, include its SSH host and project path in the
request, for example `hpc:/scratch/you/myproject`.

Setup asks where jobs should run on that cluster. It records the partition,
reservation, and account in `.claude/hpc.env`, and submissions use those values
later.

It then clones the project onto the cluster without `project_memory/` or
`wiki/`. The record stays in one place. A cluster must have a git remote so the
code can arrive with `git pull`.

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
- updates project pins and refreshes the framework-owned files — contracts,
  hooks — while a project-owned file is never written (`--dry-run` prints which
  is which).
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
- a machine with one agent, or none on PATH, completes setup.
- the fixer and the cluster support are present only when asked for.
- running setup or update a second time changes nothing.

## Migrating a project set up by an earlier version

Run the update once. It writes `.research-note/project.json` with every
integration turned on, which is what the project had. It keeps anything you
had added below a contract's project-rules heading and updates the framework
text above it. Older projects that used `.research-note/rules/` have those
appendices carried into the contract once. It replaces the git hooks with the
dispatcher, and your project's earlier hooks keep running. The record lock
moves out of `.fixer/` into `.research-note/state/`. Nothing is deleted. The
update prints one `conflict:` line for every file it could not resolve on its
own, with the command to see the difference.

Claude Code currently supports a few more setup and configuration steps than
Codex. Both agents can run jobs and write the research record.

MIT licensed.
