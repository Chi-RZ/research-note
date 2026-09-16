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

Human hand over a goal or plan, the agent excute and record the computational results and analysis for human review and correction. 

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

</details>

## 2. Configure a project

Open the directory you want to use as a research project. It can be new or
already contain code. Then tell the agent:

> set up this project with research-note

If you also need a cluster or a GitHub remote, mention it in the same request.

That runs the [`project-setup`](plugins/research-note/skills/project-setup/SKILL.md)
skill. The skill does the following.

- checks whether the directory is new or an existing project that needs
  organizing. For an existing project, it maps reusable code to `src/`, scripts
  and one-off entry points to `experiments/`, leaves large data where it is,
  and archives loose output files.
- creates `src/`, `tests/`, `experiments/`, `project_memory/`, and `wiki/`, and
  runs `git init` if needed.
- writes the project contracts, settings, and environment files under
  `.claude/`, installs the githooks, and adds the needed `.gitignore` entries.
  It also adds matching `AGENTS.md` files so Claude and Codex use the same
  instructions.
- creates the dashboard, starts the fixer and background scanner, installs the
  editor extensions when available, and runs the acceptance checks.
- registers the plugin with the other agent when both Claude and Codex are
  installed. The setup can be run again without overwriting existing project
  files.

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
- updates project pins and syncs framework files, page templates, and missing
  hooks.
- preserves project-specific settings and merges new permissions, while
  reporting drift in `hpc.env` and `.slurm` files.
- repoints `research-note.pluginRoot`, then runs doctor and both linters.

The command prints what it changed for each project. It does not stage or commit
anything, so review the output and commit the changes yourself.

Claude Code currently supports a few more setup and configuration steps than
Codex. Both agents can run jobs and write the research record.

MIT licensed.
