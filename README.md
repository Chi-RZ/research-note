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

Open the directory you want to become your research project — new or existing
— and tell the agent:

> set up this project with research-note — you can add a remote HPC and a
> GitHub repo too

That runs the [`project-setup`](plugins/research-note/skills/project-setup/SKILL.md)
skill. In one pass it:

- lays out `src/ tests/ experiments/ project_memory/ wiki/`, and `git init`s if
  there is no repo yet;
- writes the four contract files into `.claude/` and links them into the
  subtrees they govern, with an `AGENTS.md` beside every `CLAUDE.md`, so both
  agents read the same text;
- installs the githooks — one commit may touch one layer, and a record page
  that does not lint is not committed;
- generates the dashboard, and starts the background scanner that keeps it
  current;
- registers the plugin with whichever of Claude and Codex is installed and
  lacks it, so a project set up from one agent is usable from the other.

**If you run jobs on a cluster**, name it in the same sentence: the ssh host,
and where the project should live there — `hpc:/scratch/you/myproject`.

Setup asks once for that cluster's queue placement — partition, reservation,
charge account — and writes it into `.claude/hpc.env`. Every submission reads it
from there.

Setup then clones the project onto the cluster, leaving out `project_memory/`
and `wiki/`: the record lives in one place only.

**A cluster needs a git remote.** Code reaches the far side by `git pull`, never
by copying files.

## Updating

Tell the agent:

> update research-note

That runs the [`update`](plugins/research-note/skills/update/SKILL.md) skill. One pass carries the new
version into **both** agents and **every** registered project: it moves each
agent's install, repoints every project at the new plugin directory, syncs the
framework's own files while leaving yours alone, and ends on doctor and both
linters. It holds the two agents to the same source commit and prints what each
resolves to.

Nothing moves silently — read the output; it names whatever it refuses to
touch, and why.

Setup and configuration are best driven from Claude Code — a few things are
not yet fully supported in Codex. Running jobs and writing the record work
from either.

MIT licensed.
