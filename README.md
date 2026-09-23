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
  <img alt="Two lanes and two bands. Top, what only you do: hand over a goal, correct it at any step, close it, ask for a lift. Below it, what the agent does: plan, run, analyze, distil, each naming the skills it drives, with an arc returning from analyze to plan where the page decides what runs next. Beneath both, the dashboard showing what is running, unclosed and needing attention; and the linters, which check every page on each edit and commit, with the optional fixer that re-runs them and keeps the dashboard current in the background." src="docs/typical-run-light.svg" width="100%">
</picture>

## Status

This is an early release (0.x). The core is tested on Linux and macOS, but you
may still find bugs, especially in setups nobody has tried yet. It is built so
that trying it is safe:

- Nothing you wrote is thrown away. When it replaces one of your files, as with
  a `CLAUDE.md` you already had, the text is carried over first. When it cannot
  resolve a file on its own, it leaves the file as it was and says so.
- You can ask for a dry run of setup or an update, which shows every change
  before anything is written.
- Git hooks your repository already has keep running, and the plugin's own
  hooks can be removed again.
- The record is plain Markdown in your git repository.

To report a problem, open an issue with the output of `scripts/doctor.sh`, the
plugin version, and which agent you use.

## Requirements

- Claude Code or Codex
- git and Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) is recommended for your project's Python
  environment (see [Python environment](#python-environment))

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

If you use both agents, install it in each.

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
  complete and in one format;
- a dashboard of what is running and what needs your attention. Setup
  generates it; the fixer keeps it current.

If the project has a git remote, each record entry is pushed to it as soon as
it is committed. Code commits are left for you to push.

An existing project keeps its own layout. You tell the agent which directories
hold code, tests and experiments, and nothing is moved. A `CLAUDE.md` you
already had becomes the rules section, and your existing git hooks keep running.

Everything else is optional. Mention it in the same request:

| Say | You get |
|---|---|
| "with a cluster at `host:/path`" | cluster settings and job submission there |
| "with the fixer" | a background scanner that keeps the dashboard current and flags forgotten work |
| "with editor support" | VS Code extensions, including the dashboard viewer |
| "for both agents" | registration with the other installed agent |
| "we use conda" or "we use pip" | a project environment not managed by uv |

**Clusters.** Setup asks which partition, reservation and account your jobs
should use, and records them once. It then clones the project onto the cluster
without the record, so the record lives in one place. The project needs a git
remote for this, because code reaches the cluster through `git pull`.

### Python environment

uv is the default. Its lock file is what lets a recorded result be rerun in the
same environment. If your project uses conda, pip or another tool, everything
still works, but nothing can guarantee the environment can be rebuilt. The
framework says so instead of hiding it: `doctor` shows a warning, and every
job's log header states that the environment is not locked.

## 3. Update

Tell the agent:

> update research-note

This updates the plugin in each installed agent and in every project set up on
this machine. Your rules sections are kept, and a project from an earlier
version is migrated on its first update. Ask for a dry run to see the changes
first. Nothing is committed for you: review the output and commit it yourself.

MIT licensed.
