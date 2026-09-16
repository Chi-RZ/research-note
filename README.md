# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A record framework for agent-assisted computational research, for **Claude
Code** and **Codex**. It records numerical results faithfully, and distils
source code and knowledge as the work proceeds.

## What it is for

A record of computational results. The commit, recipe, machine and motivation
for each result are kept together.

A long run you supervise from a page, with each calculation tied to its goal.
Sessions may end and get compacted, but the page remains, and you review and close each
entry.

A growing record of your source code, project memory and knowledge. Your agent will grow together with you. 

A short, shareable record for collaborating with others later.

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

> set up this project with research-note

That runs the [`project-setup`](plugins/research-note/skills/project-setup/SKILL.md)
skill. In one pass it:

- lays out `src/ tests/ experiments/ project_memory/ wiki/`, and `git init`s if
  there is no repo yet;
- writes the four contract files into `.claude/` and links them into the
  subtrees they govern, with an `AGENTS.md` beside every `CLAUDE.md` so both
  agents read one text and not two;
- installs the githooks — one commit may touch one layer, and a record page
  that does not lint is not committed;
- generates the roster and the dashboard, and starts the scanner that keeps
  them current;
- registers the plugin with whichever of Claude and Codex is installed and
  lacks it, so a project set up from one agent is usable from the other;
- ends on an acceptance gate: the framework self-tests and both linters, with
  whatever still needs attention named in the output.

It never overwrites a file you already have — a re-run reports `kept`, which is
how a project picks up new scaffolding after an update. Two things are left to
you on purpose: your cluster's queue facts in `.claude/hpc.env`, and how you
pin your environment.

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

## Where to read next

| | |
|---|---|
| **Why it has this shape** | [`DESIGN.md`](DESIGN.md) — what a node, a page and an entry are, why each gate sits where it does, why there are two agents |
| **The skills** | [`plugins/research-note/skills/`](plugins/research-note/skills/) — eleven, one per moment: `plan` `objective` `analyze` `correct` `hpc-submit` `lift` `wiki-compile` `memory-lift` `reorg` `project-setup` `update` |
| **The record's exact format** | [`templates/project_memory-CLAUDE.md`](plugins/research-note/templates/project_memory-CLAUDE.md) — every field, and the linters are the final word |
| **Changing any of it** | [`CONTRIBUTING.md`](CONTRIBUTING.md) — 375 tests, `pip install pytest pyyaml`, about 30 seconds |

MIT licensed.
