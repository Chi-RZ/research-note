# research-note

[![tests](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml/badge.svg)](https://github.com/Chi-RZ/research-note/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A record framework for agent-driven computational research, for **Claude Code**
and **Codex**. It gives an agent a place to put every number it produces, and
refuses the ones that cannot be traced back.

## The problem

An agent runs for three days and reports a number. Two weeks later nobody can
say which commit produced it, at which parameters, on which machine, or what
question it was meant to answer. The session that knew has been compacted,
closed, thrown away.

The answer is not a better memory. It is that the number gets a **place** at the
moment it is produced — by the agent that produced it, with no extra human step
— and that the place is machine-checked.

## What that looks like

Every result lands as an **entry**. A linter refuses the page if any of this is
missing or malformed:

```markdown
### Entry: sampled compile cost on the 3x3 torus
- **Id:** 03.062
- **Status:** analyzed
- **Date:** 2026-09-13 22:41
- **Jobs:** 623961@gpu-a100
    Job 623961 — [log](../../../experiments/vmc/torus3/logs/slurm-623961.out)
- **Code:** `myproject@a7fcdd1` · `quimb@e63756`
- **Motivation:** `03.045` found "compilation dominates at batch 512"; does
  rounding every data-dependent shape onto a coarser grid cut compile time
  without changing the energy?
- **Recipe:** {lattice: 3x3, U: 4, batch: 512, shape_grid: 64, seed: 7}
- **Facts:** We ran one job per grid size with [run.py](...); evidence [log](...).

  | grid | compile (s) | energy |
  |---|---|---|
  | none | 412 | -8.9931 |
  | 64   |  71 | -8.9931 |

- **Conclusion:** The result shows rounding to a 64-wide grid cuts compile time
  5.8x with the energy unchanged to 1e-9, because every shape the scan meets
  collapses onto 4 variants — answers the motivation.
```

Three fields are what make it re-derivable: **`Code`** names the commits,
**`Recipe`** names every knob, **`Jobs`** names the runs and links their logs.
The linter checks they are present, well-formed, and that the SHA still resolves
on the default branch. It does not check whether the number is right — it cannot,
and the design says so out loud.

A campaign spanning weeks gets an **objective page**: one question per phase,
the entries that answered it, and a verdict the user reads instead of the
session transcript.

## What it gives you

| | |
|---|---|
| **A record with a shape** | node / page / entry — one implementation, one question, one set of runs |
| **Linters that refuse** | ~40 checks over the record and the objective pages; a page that fails does not land |
| **HPC submission** | Slurm or bare, local or over ssh, with the repo SHA, the dirty diff and every pinned fork in the log header |
| **An objective loop** | the agent launches phases, analyzes its own runs, and rewrites the plan from the page rather than from memory |
| **A scanner** | headless, flags and never repairs — the record has one writer |
| **Two agents, one core** | Claude and Codex install the same plugin; the project's contracts are one file under two names |

The framework carries **no domain ontology**. How pages group under a node is
your project's taxonomy, not ours.

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
<summary>Without an agent in the loop</summary>

The mechanical half is a plain script, and the skill only adds judgment on top:

```bash
PLUGIN=$(git config --get research-note.pluginRoot 2>/dev/null \
         || ls -d ~/.claude/plugins/cache/*/research-note/* \
                  ~/.codex/plugins/cache/*/research-note/* | sort -V | tail -1)
uv run python "$PLUGIN/scripts/bootstrap_project.py" .    # --dry-run to preview
```

Either agent's cache works — one plugin core. Afterwards everything resolves it
through `git config --get research-note.pluginRoot`.

</details>

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

<details>
<summary>Without an agent in the loop</summary>

```bash
uv run python "$PLUGIN/scripts/bootstrap_project.py" . \
    --remote hpc:/path/to/clone/on/cluster     # repeatable; first = default host
```

</details>

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

<details>
<summary>Without an agent in the loop</summary>

```bash
PLUGIN=$(git config --get research-note.pluginRoot)
bash "$PLUGIN/scripts/update_projects.sh"        # --dry-run to preview
```

Run it from the cache of the version you are moving TO: it repoints
`research-note.pluginRoot`, and a copy can only point at what it can see.

</details>

## Layout of this repo

```text
.claude-plugin/               Claude marketplace
.agents/plugins/              Codex marketplace
plugins/research-note/
  .claude-plugin/             Claude package manifest
  .codex-plugin/              Codex package manifest
  skills/                     plan · objective · analyze · correct ·
                  hpc-submit · update · project-setup · lift · reorg ·
                  wiki-compile · memory-lift
  scripts/                    the framework's programs — both linters, the record
                  bus, the launchers' record step, the cluster bridge, the
                  landing transaction, setup / update / doctor. DESIGN §10
                  lists what each is for; `scripts/tests/` is the suite
  fixer/                      headless scanner loop (a detached daemon)
  hooks/                      shared command hooks + Claude/Codex payload adapter
                  reminders, commit-prefix guard
  templates/                  shared project-side agent bindings
  editor/                     VS Code extensions — qdash (dashboard viewer),
                  markdown-white-preview (white Markdown preview on a dark theme)
```

`DESIGN.md` is the long form: what a node, a page and an entry are, why each
gate sits where it does, and why there are two agents. `CONTRIBUTING.md` is how
to change any of it. Licensed MIT.
