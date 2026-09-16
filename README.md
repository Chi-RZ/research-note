# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A record framework for agent-assisted computational research, for **Claude
Code** and **Codex**. It records numerical results faithfully, and distils
source code and knowledge as the work proceeds.

## What it is for

**Every number the code produces is placeable the moment it is produced — by
the agent that produced it, with no extra human step.** Placeable means four
things resolve from the record alone: the code (a commit), the knobs (a
recipe), the machine (an environment), and the description — what was asked and
what was found.

**An autonomous run is legible from a page, not from a transcript.** Sessions
end, get compacted, get thrown away. The objective page is what survives them,
and it is what you read to know where a campaign stands.

**The code and the understanding are distilled as the work proceeds, not
after.** A project that only accumulates entries ends with a thousand true
facts and nothing reusable, so condensation is an explicit step with its own
trigger — never a tidy-up at the end.

None of that is advice. A record page that cannot say which commit, which
knobs, which machine, and which question is refused by a linter before it
lands.

## A typical run

You hand over a goal; the agent works the loop and writes everything down.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/typical-run-dark.svg">
  <img alt="Two lanes and two bands. Top, what only you do: hand over a goal, correct it at any step, close it, ask for a lift. Below it, what the agent does: plan, run, analyze, distil, each naming the skills it drives, with an arc returning from analyze to plan where the page decides what runs next. Beneath both, the dashboard showing what is running, unclosed and needing attention; and the fixer with the linters, holding the procedure and keeping every page in one shape without repairing anything." src="docs/typical-run-light.svg" width="100%">
</picture>

The skills, in the order they appear above:
[`objective`](plugins/research-note/skills/objective/SKILL.md) ·
[`plan`](plugins/research-note/skills/plan/SKILL.md) ·
[`hpc-submit`](plugins/research-note/skills/hpc-submit/SKILL.md) ·
[`analyze`](plugins/research-note/skills/analyze/SKILL.md) ·
[`correct`](plugins/research-note/skills/correct/SKILL.md) ·
[`lift`](plugins/research-note/skills/lift/SKILL.md) ·
[`wiki-compile`](plugins/research-note/skills/wiki-compile/SKILL.md) ·
[`memory-lift`](plugins/research-note/skills/memory-lift/SKILL.md)

## Requirements and platform

**Linux and macOS.** Zero third-party runtime dependencies — standard-library
Python, POSIX shell and git. (Every lock is `fcntl.flock` through `python3`,
never `flock(1)`, which macOS does not ship.) Slurm clusters are driven **from
your machine over ssh**; nothing is installed on the cluster. GPU launching
needs a CUDA host; everything else runs anywhere.

To run the plugin: **Claude Code, Codex, or both**, plus `git` and `python3`.
To run the projects it scaffolds you will also want [`uv`](https://docs.astral.sh/uv/),
and — only if you submit to a cluster — a Slurm host reachable by passwordless
ssh. The background scanner installs as a detached daemon; nothing touches your
crontab.

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

Restart the agent once. That is the whole install — no npm package, no build
step, nothing compiled.

<details>
<summary>Other ways to point at it</summary>

The marketplace source can be a **local directory**, which is how you run a
fork or a branch you are working on:

```bash
claude plugin marketplace add /path/to/your/checkout
```

No network and no GitHub account needed — the "marketplace" is the
`marketplace.json` at the top of this repo, nothing more.

`git@github.com:Chi-RZ/research-note.git` works if you prefer ssh, and both
agents also accept the `Chi-RZ/research-note` shorthand.

Both agents read their own manifest — Claude `.claude-plugin/marketplace.json`,
Codex `.agents/plugins/marketplace.json` — and both declare the marketplace
`rzchi`, so one selector works on either side. Step 2 registers the second
agent for you if it finds one, reading that name back from whichever side it
just added rather than assuming it: the name belongs to whoever ran
`marketplace add`, not to this repo.

</details>

## 2. Configure a project

Open the directory you want to become your research project — new or existing
— and tell the agent:

> set up this project with research-note

That runs the [`project-setup`](plugins/research-note/skills/project-setup/SKILL.md) skill: it lays the
layout down, wires both agents' contracts and skills to one copy each, installs
the commit-prefix githook, starts a background scanner that watches the record
and repairs nothing, and refuses to report success until the self-tests and
both linters pass. Then it walks you through the parts no script can decide —
the project's mission, what to do with code that is already there, pinning the
environment.

It is idempotent. Existing files are kept, never overwritten; run it again
after any plugin update.

**The one thing you must supply** is `.claude/hpc.env` — the machine facts
nothing can infer. Working purely locally needs nothing in it.

<details>
<summary><code>.claude/hpc.env</code> — what goes in it</summary>

The file bootstrap writes documents every key in its own comments; this is the
shape:

```sh
# a remote Slurm cluster (omit the whole block to work purely locally)
REMOTE_HOST=hpc                 # ssh alias; `ssh -o BatchMode=yes hpc` must work
REMOTE_DIR=/path/to/clone/on/cluster
REMOTE_PARTITION=...            # queue placement, applied by the submit step
REMOTE_ACCOUNT=...              #   so no submit file has to carry it

# a library you are DEVELOPING, so its checkout can be found on each side
LIB_mylib_LOCAL=/home/you/pyenv/mylib
```

Several clusters: list them in `REMOTE_HOSTS` and give each a
`REMOTE_DIR_<host>`. All of them are watched equally; `REMOTE_HOST` is only the
default when a command does not name one.

</details>

<details>
<summary>The Python environment</summary>

A normal `uv` project: `pyproject.toml` + `uv sync`. Forks are **pinned by git
commit** (`tool.uv.sources: mylib = {git = "...", rev = "<sha>"}`), so every
machine builds the identical library from the pin — no checkout layout to
replicate — and the log header records the rev. `scripts/bump_lib.sh` advances
a pin and refuses a dirty or unpushed fork. `remote.sh push` checks pin
freshness and environment parity before anything queues.

</details>

## 3. Wire a cluster (optional)

The cluster syncs from GitHub, so the project needs an `origin` first. Then
tell the agent:

> wire this project to the cluster at hpc:/path/to/clone

Each cluster gets a sparse clone — it runs jobs, so it never needs the record,
the wiki or the contracts. From then on a remote launch is one action: commit,
push, ff-pull, SHA check, `sbatch`, and the job id lands on its entry here. It
refuses if anything is dirty or diverged.

**Nothing is installed on the cluster and no agent runs there.** Code goes out,
logs and data come back, and every judgement is made on this side.

Details: [`hpc-submit`](plugins/research-note/skills/hpc-submit/SKILL.md).

## 4. Verify

```bash
# linters green on the freshly scaffolded record?
uv run python "$PLUGIN/scripts/check_node_page.py" project_memory/nodes/root/node.md

# fixer alive? (the daemon; state in .fixer/)
crontab -l | grep fixer || cat .fixer/cron.log

# remote wired? (only if you did step 3)
bash "$PLUGIN/scripts/remote.sh" status
```

Then open `project_memory/dashboard.html` (or the qdash panel in VS Code) and
start with `research-note:plan` — your first node, its gate page, and its first entry.

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
| **Changing any of it** | [`CONTRIBUTING.md`](CONTRIBUTING.md) — 373 tests, `pip install pytest pyyaml`, about 30 seconds |

MIT licensed.
