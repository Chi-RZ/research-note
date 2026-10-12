# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[![Homepage ↗](docs/project-homepage.svg)](https://chi-rz.github.io/research-note/) ·
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
  environment with it. If it is missing, setup asks before installing it.

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

Open your project directory and tell the agent:

> set up this project with research-note

Setup proposes a layout for you to confirm, preserving existing code and
project rules. By default, you get:

- `project_memory/` for objectives, research records and shared memory;
- shared instructions for Claude Code and Codex;
- Git hooks and linters that keep the record consistent.

Dashboard, cluster access, the background fixer and editor support are optional.
Ask for them in the same request. Existing projects keep their enabled features.

With a Git remote, record entries are pushed automatically after committing;
code commits are left for you to push.

See [setup options](plugins/research-note/skills/project-setup/SKILL.md) and
[environment details](plugins/research-note/skills/project-setup/environment.md)
for uv, external editable libraries and cross-machine setup.

## 3. Update

In a project, tell the agent:

> update research-note

This fetches remote main and updates the current project's Claude, Codex and
project tools together. Other projects keep their selected versions.
Reload Claude with `/reload-plugins`; start a new Codex session.

You can also ask for a version (such as `0.1.0`) or an update from a local
checkout. Local updates include uncommitted plugin edits. The update reports
which version and build were selected.

See [installation details](DESIGN.md#12-projects-select-shared-releases) for
shared caches and restoring a cloned project.

MIT licensed.
