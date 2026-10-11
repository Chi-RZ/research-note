# Research Project

This file is the **root contract**: doctrine and pointers — the rules no linter
can decide, and where everything else lives. Every skill that says "root
contract" means this file. Detail belongs to the contract of the subtree you are
working in. Before editing a scoped directory, read its `CLAUDE.md` as Claude or
its `AGENTS.md` as Codex.

## Layers

One monorepo. A layer is a path plus the commit prefix that may touch it; a hook
refuses a mismatch.

| path | holds | prefix |
|---|---|---|
| `<library-root>` `<test-root>` | capabilities that outlive one experiment, each with a test | `feat:` `fix:` `refactor:` |
| `<experiment-root>/<node>/` | `impl/` the implementation · `<group>/` how it is invoked, and its outputs | `exp(<node>):` |
| `project_memory/` | the record: `nodes/` facts · `objectives/` intent · `note/` understanding · `memory/shared/` shared agent memory | `memory:` |
| `<knowledge-root>/` | the published knowledge base, self-contained | `wiki:` |
| `.claude/` | this project's bindings | `agent:` |
| root-level files only | `.gitignore`, `pyproject.toml`, a root doc — never a directory | `chore:` |

**`.research-note/project.json` is the path authority, and it decides only the
four placeholders above.** They are whatever `roles.libraries`, `roles.tests`,
`roles.experiments` and `roles.knowledge` declare — `src/`, `tests/`,
`experiments/` and `wiki/` for a project that declares nothing, one or several
directories each, printed by `python3 "$PLUGIN/scripts/project_config.py" role
<name>`. **Everything else named in this contract is the framework's and never
moves**: `project_memory/` and its subtree, the agent bindings, the conventions
inside a node, and these prefixes. A top-level directory that fits no layer
becomes a NEW layer with its own prefix, declared in the same file; `chore:` is
not the bucket for it.

A lift lands as a `feat:` plus an `exp(<node>):` — two layers in one change
means two commits, the second naming the first. Record commits carry id
trailers, per `project_memory/CLAUDE.md`.

Condensation is always an explicit pump: `lift` code into `<library-root>` when a
second consumer appears; `wiki-compile` a note or a closed entry into the wiki
and `memory-lift` a memory into a skill, both when the user asks.

## The record

**A node is one implementation, frozen in behaviour.** The test when its code
changes: *does some knob setting on the new code reproduce the old recorded
result?* Yes → the same node, and the edit owes a **validation entry** naming the
entry it replays, the recipe, and the number it reproduced. No → a new node, the
old one left standing under the entries that closed on it. The claim covers
everything the node executes, including the shared libraries it imports.

**A page is one question asked of a node.** Where a new run goes: *if the page's
title still describes what you are about to run, it is another entry there; if you
would have to rewrite the title, it is a new page.* Pages about the code — the
gate, the validations — sit directly under the node; a page about running it sits
under the group of the instance it ran on, and a cross-group comparison sits at
node level.

**An entry is a set of computations that ran one piece of code following one
procedure.** A parameter scan is a single entry, one job per point. Different
code, or a probe whose motivation could not have been written before seeing the
previous result, makes a different entry.

**The record, not the file, preserves a result.** A page quotes the number and
scripts are in git, so a result file may be rewritten; a checkpoint is
overwritten only by its own later state.

**Motivation and Recipe are fixed; Facts move only toward what happened; only
the Conclusion is rewritten freely.** The lifecycle stops one step short of
done: you take an entry to `analyzed` and write its conclusion — **only the
user closes**.

**A long goal gets an objective page**, and it is the interface — the user reads
the page, not the session. Its Goal is the user's and changes only on their explicit instruction;
its Plan is one block per phase, a phase being ONE question with the entries that
answered it; its Verdict is the current answer, in a few lines. The Plan is
rewritten freely — appended, renumbered, dropped; git holds every route it used
to show. Pages and phases cut differently: the page belongs to the code and
outlives the goal, the phase belongs to the goal and dies with it.

Format, field by field — entry and objective alike: `project_memory/CLAUDE.md`.

## The workflow

The agent's place is on a page, so after any interruption the move is the same:
re-read the page, and go on from where it says the work stands.

- **The next move comes from the objective page.** Between actions the agent
  re-reads the Plan; the next phase is decided from the concluded readings, and
  the Plan moves to match before anything runs. Every phase whose dependencies
  are met launches at once, one agent each.
- **Read-first, at every entrance** — an entry opening or being picked up from
  someone else (whatever the predecessor knew and did not write down is gone),
  and a phase deciding what comes next: `_index.md`, the touched nodes'
  conclusions, then `memory/shared/MEMORY.md` and
  `<knowledge-root>/knowledge/index.md`, opening only the rows that name what
  you are about to touch. An entry asks
  *has this been run, how much do two identical runs differ, what number does it
  have to beat*; a phase asks *what is already settled, and what was ruled out*.
  A recorded answer finishes the request or shrinks it to the part that is new.
  This list lives here and nowhere else — a skill says "read-first" and adds
  what its own job needs, never its own copy of these four.
- **`wake-me-if` fires → the loop stops**, sets `attention:` and waits.
- **A correction is applied at once**; a question is answered from the record
  and does not interrupt the open phase.
- **A dependency change is prospective.** Existing entries remain valid for
  the commits they cite. Before a new recorded run, diff the old and new
  dependency, map the changed code to actual imports and calls, then run the
  smallest affected test or sentinel. Expand only when that check moves, the
  objective asks for a new-version claim, or a confirmed old-version bug
  invokes `research-note:correct`; a SHA change alone schedules no reruns.

## Stop and ask

| before | because |
|---|---|
| opening a new node, when the reproduce test does not settle it | once entries close on it the split is permanent |
| closing an entry | writing a conclusion is "I measured, I judge"; closing is "I accept" |
| lifting a note into the wiki, or a memory into a skill | an agent that generalises its own habits compounds its own mistakes |

## Running things

`command -v sbatch` → a Slurm cluster, where compute runs inside an allocation,
never on the login node; nothing → a bare server. Every background or batch
launch goes through **`hpc-submit`**, which owns dispatch, GPU assignment and
OOM retry, log naming and headers, job-start verification and the submit
record; a quick foreground smoke run does not.

## Sharing the repo

- **One live record, one door.** `project_memory/` exists once, in the main
  checkout on the default branch. Writes go through `record_sync.sh`, which
  refuses a concurrent edit rather than overwriting it. A session that cannot
  edit the checkout edits a SCRATCH copy (under /tmp) and `put`s it — a
  record write never needs a worktree, and worktrees carry no record.
- **One entry, one writer.** Whoever launches a probe writes that entry.
- **Retiring a worktree is about processes, not about git.** Removing one
  while its agent is still running fails silently: the agent's paths resolve to
  the main checkout and it keeps committing there, to main, for the rest of its
  run, found only by reading history afterwards — and `git worktree remove`
  cannot see it. `scripts/worktree_retire.sh <path>` refuses while any process
  has its cwd inside. Worktree landing is complete only after a main-checkout
  session runs that script once the worktree's processes have exited.
- **Isolation follows concurrency.** A code-editing agent uses its own
  worktree when another agent may write the checkout, when main is dirty with
  work it does not own, or when the change needs an isolated branch. A sole
  agent may make a short change directly in a clean main checkout. Worktree
  landing is `merge --ff-only`; a diverged branch REBASES onto main first.
  Branches land small and often — hours, not weeks. A worktree session's
  non-record change that belongs on main (`.claude/` bindings, a contract
  file) is HANDED to a main-checkout session for its own `agent:` commit —
  until the branch lands, the whole machine would read the stale copy.
- **Landing and launching in one breath is one transaction.** An agent that
  lands its own branch and then launches its own recorded job runs
  `scripts/land_and_launch.sh`, which holds one lock across rebase → merge →
  launch and launches from main because the launcher refuses a worktree. Git
  coordinates two agents' rebase and ff-merge, but main's WORKING TREE is not
  safe: `merge` rewrites the files the launcher reads to build its log header,
  so a merge landing mid-launch records a SHA and a dirty diff for a tree that
  never ran — a failure in the record, not in git, that nothing later detects.
- **Formal runs launch from main** — a branch smoke certifies only the impl plus
  the shared library code it branched from.

## Writing code

`<library-root>` is the abstraction layer, not a deduplication target: it holds
designed interfaces, `<experiment-root>` holds the composition that calls them.
Before writing anything new, look in this order — the project's domain library
(named at the top of `<library-root>/INDEX.md`), then that index itself, then
every experiment root for prior art. A capability a second experiment needs is
**lifted**, never copied. `<library-root>/INDEX.md` and
`project_memory/_index.md` are regenerated views (`gen_index.py`) — never
hand-edit either. **Regenerate the index in the MAIN checkout whenever
`<library-root>` moves** — a worktree here is sparse and generates a short index
— and a pre-commit gate refuses a commit touching it while the index is behind:
an index missing a capability is how the same thing gets written twice.

New function → its test first. Modify `<library-root>` → update its test in the
same change. One test file per source file, mirrored under `<test-root>`;
experiment-level tests live in `<experiment-root>/tests/`.

Two that cost real work when forgotten: run Python through the project's
runner and keep its `-u` — `uv run python -u` unless `environment` in
`.research-note/project.json` declares another — or the log stays empty until
the job ends; `git add` a file as soon as you write it.

## If the working tree has changes you did not make

Ask what they were and why before building on them or reverting them.

## Pointers

| | |
|---|---|
| entry and objective format, lifecycle, job rules | `project_memory/CLAUDE.md` |
| node layout, run scripts, log naming, outputs | `<experiment-root>/CLAUDE.md` |
| what makes a wiki page publishable | `<knowledge-root>/CLAUDE.md` |
| the linters and every other framework script | `PLUGIN="$(git config --get research-note.pluginRoot)"` — this project's selected release, written by setup/update. If missing, restore its lock using the installed `update` skill before running project tools. |

---

## Project-specific rules

Write rules for this project below this heading. This section belongs to the
project and is kept when the plugin updates the framework section above. A rule
that would serve every project belongs in the plugin template instead.
