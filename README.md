# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**[Project homepage](https://chi-rz.github.io/research-note/)** ·
**[3×3 TFIM example](examples/tfim-simple-update/)**

A record framework for agent-assisted computational research, for **Claude
Code** and **Codex**. It records numerical results faithfully, and distils
source code and knowledge as the work proceeds.

The [3×3 TFIM example](examples/tfim-simple-update/) is a complete small
project with two objectives, a locked uv environment, Quimb simple update,
QuSpin exact diagonalization, recorded evidence and compiled wiki knowledge.

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
  <img alt="Two lanes and two bands. Top, what only you do: hand over a goal, correct it at any step, close it, ask for a lift. Below it, what the agent does: plan, run, analyze, distil, each naming the skills it drives, with an arc returning from analyze to plan where the page decides what runs next. Beneath both, the optional dashboard showing what is running, unclosed and needing attention; and the linters, which check every page on each edit and commit, with the optional fixer that re-runs them in the background." src="docs/typical-run-light.svg" width="100%">
</picture>

## Requirements

- Claude Code or Codex
- git and Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) — the plugin manages your project's Python
  environment with it (see [Python environment](#python-environment)). If it is
  not installed, setup offers to install it.

## 1. Install

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

Install in the agent you use for setup. Setup prepares project bindings for
both Claude and Codex. Start a fresh session in the other agent and accept its
plugin or hook trust prompt; in Codex, `/hooks` shows hooks awaiting review.

## 2. Set up a project

Open the directory you want to work in, new or with existing code, and tell the
agent:

> set up this project with research-note

The agent shows how it will map your directories and asks you to confirm before
it writes anything. You get:

- the record, `project_memory/`, where every result gets a page;
- one instruction file per directory, read by Claude as `CLAUDE.md` and by
  Codex as `AGENTS.md`, with a section at the end for your project's own rules;
- git hooks that keep each commit to one part of the project;
- checks, run on every edit and every commit, that keep each record page
  complete and in one format.

If the project has a git remote, each record entry is pushed to it as soon as
it is committed. Code commits are left for you to push.

Setup runs bootstrap once, then a read-only installation check. A dry run is
available on request; doctor is used for diagnosis if a check fails.
Dashboard generation is off for new projects. Existing projects keep their
previous behavior until explicitly disabled with `--no-dashboard`.

An existing project keeps its own layout. You tell the agent which directories
hold code, tests and experiments, and nothing is moved. A `CLAUDE.md` you
already had becomes the rules section, and your existing git hooks keep running.
Setup does not reorganize your code; if you later want the default layout, move
things yourself in an ordinary commit.

Everything else is optional. Mention it in the same request:

| Say | You get |
|---|---|
| "with a dashboard" | an HTML status view, refreshed after record writes |
| "with a cluster at `host:/path`" | cluster settings and job submission there |
| "with the fixer" | a background scanner that flags forgotten work and keeps job status current |
| "with editor support" | VS Code extensions; also request the dashboard to use its viewer |
| "for both agents" | both project bindings are already included; each host loads the pinned plugin |

**Clusters.** Setup asks which partition, reservation and account your jobs
should use, and records them once. It then clones the project onto the cluster
without the record, so the record lives in one place. The project needs a git
remote for this, because code reaches the cluster through `git pull`.

### Python environment

uv manages it. `pyproject.toml` and `uv.lock` are committed; each machine builds
its own `.venv` from them, jobs run through `uv run`, and every job's log header
names the lock it ran under. That lock is what lets a recorded result be rerun
in the same environment. Setup installs uv if it is missing, after asking you.

An external library under active development can stay editable without using
the same filesystem layout on every machine. Its real paths live in the
gitignored `.research-note/editables.env`; uv uses a stable project-local slot,
and `remote.sh push` synchronizes the commit through its Git remote or, when it
has none, a Git bundle over SSH.

## 3. Update

In a project, tell the agent:

> update research-note

It fetches the published release and updates **this project only**. Claude and
Codex both use the project's locked version: skills, lifecycle hooks, scripts
and Git hooks move together. Other projects and user-level plugin installations
are unchanged. Claude can run `/reload-plugins` to switch in place; start a new
Codex session to use the update.

The lock is `.research-note/plugin-lock.json`. Installed releases live once per
machine in `~/.local/share/research-note/releases/<digest>/`; projects selecting
the same content share that installation. Claude uses a native project-scope
installation; Codex selects it through project configuration and keeps its own
cache. User-level enablement stays unchanged. Available hosts are verified;
missing hosts or an untrusted Codex project are reported as pending.

Ask for a specific version, or update from an unpublished local checkout:

```bash
bash "$PLUGIN/scripts/update_projects.sh" --version 0.1.0 PROJECT_DIR
bash "$PLUGIN/scripts/update_projects.sh" --source /path/to/repo/plugins/research-note PROJECT_DIR
```

Setup reuses an existing selection. Updates preserve project rules, stop on
contract conflicts and restore previous bindings on failure. Legacy project
runtime copies are removed after migration; shared releases remain available
for other projects. Switching a source checkout's branch does not change an
installed release. The version and content hash show exactly which build is used.
Version tags must include this shared-install mechanism; older private installers
are refused before switching. Existing legacy projects can migrate explicitly.
A new clone needs its selected release restored before the agents can load it:
run `project_runtime.py restore --source /path/to/matching/plugin` from the
project using a copy of the plugin with the locked content digest. For a moved
checkout whose shared release is present, `restore` refreshes local paths.
It refuses a different version instead of silently upgrading.


MIT licensed.
